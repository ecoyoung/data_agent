**简体中文** | [English](README.md)

# Data Detector

Data Detector 是一个基于 FastAPI 的飞书数据助手，用于 Amazon 业务分析。用户在飞书中用自然语言提问；服务将问题关联到结构化的 Amazon 中间层目录（catalog），生成只读 PostgreSQL SQL，在安全检查后执行，并以飞书卡片、表格和图表的形式回复。

当前主要数据源是 `intermediate_amazon_` 表/视图族，覆盖多个品牌、店铺、市场和报表领域。

## 架构

```text
Feishu user
  -> Feishu encrypted webhook
  -> FastAPI /feishu/webhook
  -> message idempotency + session routing
  -> deterministic brand/scope alias resolution
  -> clarification / intent detection
  -> progressive disclosure catalog loading
  -> LLM SQL generation
  -> SQL repair + safety checker + business checker
  -> read-only PostgreSQL execution
  -> policy-driven chart/table/card rendering
  -> query log + feedback loop
```

关键运行时分层：

- `src/data_agent/feishu/`：飞书 webhook 处理、卡片构建和消息发送。
- `src/data_agent/agent/`：LLM 客户端、prompt 构建器、意图检测、SQL 修复、SQL 检查器、SQL 执行器以及 few-shot 检索。
- `src/data_agent/data_catalog/`：机器可读目录、指标规则、表元数据、AI_HINT 族规则、join 关系、模板和语义路由索引。
- `src/data_agent/session/`：内存中的会话历史，以及 SQLite 查询/反馈日志。
- `src/data_agent/visualization/`：图表渲染和适配飞书的表格格式化。视觉样式由 `chart_policy.json`（主题配色、图表数量限制、指标颜色映射）和 `policy.py`（`infer_chart_spec` → `ChartSpec`）固定；`recipes/` 下的命名配方（如 `monthly_mom_sales_units`）在回退到通用折线/柱状/表格渲染器之前处理特定的字段组合。LLM 从不决定视觉样式。

## 渐进式披露（Progressive Disclosure）

prompt 分层构建，而不是一次性 dump 整个 schema：

1. 确定性的品牌/范围别名解析，例如 `BKN US` -> Beekeeper US 范围。
2. 意图检测：趋势、排名、对比、明细、汇总或自动。
3. 结构化规则：业务默认值、向用户追问规则、禁止的 SQL 规则。
4. 表路由：关键词打分、范围别名和轻量级语义索引。
5. 对于较宽的候选表集合，可选地进行 LLM 表筛选。
6. 从 `tables_columns.json` 进行列裁剪。
7. 条件性的关系、模板和 few-shot 示例。

完整设计见 [docs/progressive_disclosure.md](docs/progressive_disclosure.md)。

## 安全

SQL 执行由以下措施守护：

- 只读 PostgreSQL 连接设置；
- 语句超时和最大返回行数；
- 写入关键字阻断；
- 强制单条 SELECT/WITH 语句；
- 目录表白名单；
- 列存在性检查；
- 业务规则，例如必需的日期过滤、指标默认值和禁止的聚合模式；
- 针对已知安全改写的确定性 SQL 修复，例如 `ROUND(..., n)::numeric`、按月 `GROUP BY 1` 以及文本日期转换。

## 并发

该服务面向单容器 MVP 设计：

- 飞书重复消息投递会按消息 id 持久化并去重。
- 慢速的 LLM/SQL/卡片工作在线程池中运行，不会阻塞异步 webhook。
- 每个会话内的查询串行执行，避免历史记录竞态。
- 全局查询并发受 `MAX_CONCURRENT_QUERIES` 限制。

参见 [docs/concurrency_architecture.md](docs/concurrency_architecture.md)。

## 可视化策略

图表视觉样式与 LLM 解耦。查询结果按以下流程处理：

1. `infer_chart_spec(user_text, data, columns)` 将结果分类为 `kpi`、`table`、`line`、`bar` 或某个命名配方。
2. `src/data_agent/visualization/recipes/` 下的命名配方（如 `monthly_mom_sales_units`）匹配固定的字段组合，并拥有专属的双轴/带标注渲染。
3. 否则，通用渲染器回退到策略驱动的折线/柱状/表格，语义颜色来自 `chart_policy.json`。

主题、配色、最大系列数、Top N、字体栈和指标颜色映射全部位于 `chart_policy.json`；LLM 从不决定视觉样式。参见 [docs/chart_catalog.md](docs/chart_catalog.md)。

## 仓库结构

```text
.
├── src/data_agent/              # application package
│   ├── main.py                  # FastAPI app and health endpoint
│   ├── config.py                # settings and env loading
│   ├── agent/                   # LLM, prompt, SQL repair/check/execute
│   ├── data_catalog/            # Amazon intermediate catalog and rules
│   ├── feishu/                  # webhook, cards, sender APIs
│   ├── session/                 # history and query/feedback logs
│   └── visualization/           # charts, table formatting, and policy
│       ├── chart.py             # matplotlib rendering entrypoint
│       ├── chart_policy.json    # fixed theme, palette, chart limits
│       ├── policy.py            # infer_chart_spec → ChartSpec
│       ├── formatting.py        # metric value/axis formatters
│       └── recipes/             # named chart recipes (monthly_mom, theme, ...)
├── tests/                       # automated tests
├── scripts/                     # catalog, regression, metrics, maintenance
├── evals/                       # business SQL regression cases
├── docs/                        # architecture and data catalog docs
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml
```

## 配置

将 `.env.example` 复制为 `.env`，并填入飞书、LLM、PostgreSQL 和 Cloudflare 的相关值。

重要设置：

- `DEEPSEEK_API_KEY`
- `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`
- `SQL_TIMEOUT`
- `MAX_ROWS`
- `MAX_CONCURRENT_QUERIES`
- `QUERY_LOG_DB_PATH`

不要提交 `.env`、`postgresql.env` 或 `storage/`。

## 本地运行

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn data_agent.main:app --host 0.0.0.0 --port 8000
```

## 使用 Docker 运行

```bash
docker compose up -d --build data-agent
curl http://127.0.0.1:8010/health
```

当 `.env` 中的值发生变化时，请重建容器，以便 Docker 重新加载 `env_file` 的值：

```bash
docker compose up -d --force-recreate data-agent
```

## 验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_business_sql_cases.py --execute
```

目录维护：

```bash
.venv/bin/python scripts/build_intermediate_catalog.py
.venv/bin/python scripts/build_scope_aliases.py
.venv/bin/python scripts/build_table_semantic_index.py
.venv/bin/python scripts/validate_business_sql_cases.py --execute
```

运维审查：

```bash
.venv/bin/python scripts/metrics.py --days 7
.venv/bin/python scripts/review_feedback.py --days 7
.venv/bin/python scripts/generate_regression_candidates.py --days 7
```
