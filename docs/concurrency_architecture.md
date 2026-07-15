# 并发与上线前架构加固

最后更新：2026-07-14

## 当前目标

真实用户测试前，先保证单机/单容器场景下不会因为重复投递、并发会话、慢 LLM/SQL 调用和 SQLite 写入冲突导致明显错误。

本阶段不引入 Redis、Celery、外部队列或多副本状态同步；先把当前服务加固到可控的单实例并发模型。

## 已完成

### 1. 飞书消息持久化幂等

关键文件：
- `src/data_agent/session/query_log.py`
- `src/data_agent/feishu/webhook.py`

新增 `message_event_claims` SQLite 表，用 `message_id` 做主键。每条飞书消息进入处理前必须先原子 claim：

- claim 成功：创建对应 `query_events`，继续处理。
- claim 失败：说明是飞书重复投递或并发重复处理，直接返回 `{"code": 0}`。

这样去重不再依赖进程内 set，服务重启后仍然能识别已处理消息。

### 2. 慢处理链路线程池隔离

FastAPI webhook 仍是 async handler，但 LLM、SQL、飞书发卡片等同步慢操作通过 `run_in_threadpool()` 执行，避免长查询或 LLM 超时阻塞事件循环。

### 3. 会话历史加锁

关键文件：
- `src/data_agent/session/manager.py`

内存会话历史增加 `RLock`，保护 `get_history`、`add_to_history`、`clear_session`、`cleanup_expired`。

### 4. 查询并发上限

关键文件：
- `src/data_agent/config.py`
- `src/data_agent/feishu/webhook.py`

新增配置：

```env
MAX_CONCURRENT_QUERIES=4
```

默认最多同时处理 4 个查询。超过上限时不进入 LLM/SQL 链路，直接返回“系统正在处理较多查询，请稍后重试”，并在 query log 中记录 busy error。

### 5. Session 级互斥

关键文件：
- `src/data_agent/feishu/webhook.py`

同一个 session 同时只允许一个查询进入 LLM/SQL 链路。若上一条查询仍在处理，后续同 session 请求会快速返回“这个会话上一条查询还在处理，请稍后再发送下一条”，并在 query log 中记录 `session busy`。

这个策略保护了多轮上下文：

- 避免第二条追问读取到第一条尚未写完的 history。
- 避免两条并发结果交叉写入同一个 session。
- 不影响不同 session 之间并行，仍由全局 `MAX_CONCURRENT_QUERIES` 控制总量。

## 当前仍需注意

1. 会话历史仍是进程内状态，多 worker 或多副本会导致上下文不共享。
2. `message_event_claims` 解决的是同一 SQLite 存储下的幂等；如果未来多副本不共享 storage，需要迁移到 Redis/Postgres。
3. 当前超过全局并发上限或 session busy 都是快速失败，不排队；真实测试后可根据使用体验决定是否改成后台队列。
4. LLM 客户端仍是每次请求创建，后续可评估复用 client 或增加 provider-level retry/backoff。

## 下一阶段候选

- 增加后台作业队列：webhook 快速 ack，查询完成后主动发卡片。
- 将 session store 从内存迁移到 SQLite/Redis。
- 对 DB 查询和 LLM 调用分别设置独立 semaphore，避免某一类资源被打满。
- 增加 `/health` 以外的 `/ready`，检查 DB、query log、LLM 配置和 Catalog 文件可读性。
