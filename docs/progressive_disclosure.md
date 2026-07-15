# 渐进式披露（Progressive Disclosure）架构

本文档记录数探 Text-to-SQL 的渐进式披露架构：每一层只在必要时披露必要信息，避免把 462 张中间表、全部列、全部规则和全部示例一次性塞进 LLM context。

参考：[Pinterest Text-to-SQL](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)、[PSM-SQL](https://arxiv.org/html/2502.05237v1)、[RSL-SQL](https://arxiv.org/html/2411.00073v1)。

**最后更新**：2026-07-14  
**当前全量测试**：153 passed

---

## 当前架构

```
用户问题
   │
   ▼
[Intent] 查询意图识别
   │   trend / ranking / comparison / detail / summary / auto
   ▼
[Rules] 结构化业务规则
   │   business_rule / ask_user_about / auto_mapping / forbidden_sql
   ▼
[Layer 1] 关键词 + scope alias + 本地语义索引粗筛表
   │   select_catalog_table_docs / _score_table / table_semantic_index.json
   ▼
[Layer 2] LLM 复筛表（候选 >2 时）
   │   refine_tables_via_llm
   ▼
[Layer 3] 列级裁剪
   │   column_selector.select_columns
   ▼
[Layer 4] 条件加载关系、模板、示例
   │   relationships / query_templates / similar successful SQL
   ▼
LLM 生成 SQL
   │
   ▼
[Repair] 执行前机械修复
   │   ROUND numeric cast / GROUP BY month -> GROUP BY 1
   ▼
[Checker] 安全、Schema、业务规则校验
   │   validate_sql / check_column_existence / check_business_rules
   ▼
执行 SQL
   │
   ├─ 成功 → 按 intent 展示：折线图 / 柱状图 / 表格 / 单值卡
   │
   └─ 失败 → LLM 单次重写 SQL → 再走 Repair + Checker + Execute
```

## 核心原则

- 准确率不靠 LLM 猜，而靠机器可读业务规则、结构化 Catalog、SQL checker 和回归闭环。
- Markdown 给人看，JSON 给程序消费；同一条规则应尽量由 prompt、clarifier、checker 共用。
- 真实错误必须沉淀成规则、模板、repair、checker 或 eval，不能只靠临时 prompt 修补。

---

## 已完成能力

### PD-1：列级裁剪

目标：只给 LLM 需要的表和列。

关键文件：
- `src/data_agent/data_catalog/tables_columns.json`
- `src/data_agent/agent/column_selector.py`
- `src/data_agent/agent/prompt_builder.py`

列选择逻辑：
- 必带日期字段、业务键、必需过滤字段。
- 根据 `metric_synonyms.json` 做指标同义词匹配。
- 根据用户问题和列名/描述做 token 重叠。
- 根据公式补齐依赖列，例如 ACoS 需要 `ams_spend` 和 `ams_sales`。

### PD-2：LLM 表复筛

目标：候选表过多时，用一次小 LLM 调用挑真正相关表。

关键文件：
- `src/data_agent/agent/prompt_builder.py:refine_tables_via_llm`
- `src/data_agent/feishu/webhook.py:_maybe_refine_tables_via_llm`

触发条件：候选表数量大于 2。失败、超时或解析不到表名时回退到关键词筛选结果。

### PD-3：Schema 自检

目标：执行前拦截幻觉列和 Catalog 外表。

关键文件：
- `src/data_agent/data_catalog/allowed_columns.json`
- `scripts/build_allowed_columns.py`
- `src/data_agent/agent/sql_checker.py`

当前策略：重点校验限定列引用，例如 `t.column`。裸列名仍以 SQL 执行和业务规则为主，避免误伤函数、别名和 SQL 关键字。

### PD-4-lite：本地语义检索增强

目标：在不依赖外部 embedding 服务的前提下，增强长尾问法的表路由稳定性。

关键文件：
- `scripts/build_table_semantic_index.py`
- `src/data_agent/data_catalog/table_semantic_index.json`
- `src/data_agent/agent/prompt_builder.py:_semantic_score_table`

当前策略：
- 离线读取 `tables_metadata.json`、`tables_columns.json`、`scope_aliases.json`，生成每张表的加权 semantic tokens。
- 运行时 `_score_table` 在现有关键词、scope alias、domain hints 基础上追加一个 capped semantic score。
- scope/品牌 alias 仍由专用 scope alias 规则处理，不在 semantic index 里重复高权重加分，避免同品牌所有表一起被抬高。
- 泛销售、营收、GMV 在没有明确 Business Report / sessions / 流量 / 转化 / 购物车语义时，继续偏向 `intermediate_amazon_3p_orders_*_view` 和 `ordered_revenue`。
- 购物车、sessions、page views、转化等语义路由到 `intermediate_amazon_3p_sales_and_traffic_*_view`。

未来可选：如果长尾问题继续增加，可在此基础上替换为真正 embedding/向量相似度；保留关键词分作为 fallback。

### PD-5：历史成功 SQL few-shot

目标：从 `query_logs.sqlite3` 找相似成功问题，作为格式参考。

关键文件：
- `src/data_agent/agent/query_examples.py`
- `src/data_agent/agent/prompt_builder.py:_format_few_shot`
- `src/data_agent/feishu/webhook.py:_maybe_find_few_shot_examples`

注意：few-shot 只作格式参考，不允许覆盖当前 Catalog 规则和用户意图。

### PD-6：自动修复与单次重试

目标：减少用户直接看到 SQL 错误。

关键文件：
- `src/data_agent/agent/sql_repair.py`
- `src/data_agent/agent/sql_executor.py`
- `src/data_agent/feishu/webhook.py:_repair_sql_via_llm`

已支持：
- `ROUND(expr, n)` 自动补 `::numeric`。
- 月度 `GROUP BY month` / `ORDER BY month` 自动改为 `GROUP BY 1` / `ORDER BY 1`。
- 首次执行失败后，带用户问题、失败 SQL 和错误信息让 LLM 只重写 SQL 一次。
- 重写 SQL 仍走同一套安全校验、业务规则校验和只读数据库连接。

### PD-7：离线评估与回归闭环

目标：真实失败和反馈能沉淀成测试资产。

关键文件：
- `evals/innerbrightness_business_questions.json`
- `evals/query_log_regression_candidates.json`
- `scripts/validate_business_sql_cases.py`
- `scripts/generate_regression_candidates.py`
- `scripts/promote_regression_candidate.py`

当前闭环：
1. `generate_regression_candidates.py` 从 query log 和反馈生成候选。
2. 人工审核候选 SQL 和业务口径。
3. `promote_regression_candidate.py` dry-run 预览。
4. 显式 `--confirm --confirm-reviewed` 后追加到正式 eval。
5. `validate_business_sql_cases.py --execute` 实际执行正式回归。

### 结构化规则层

目标：把散落在 prompt、clarifier、checker 的规则收敛为机器可读规则。

关键文件：
- `src/data_agent/data_catalog/rules.json`
- `src/data_agent/data_catalog/__init__.py:load_catalog_rules`
- `src/data_agent/data_catalog/__init__.py:render_catalog_rules_for_prompt`
- `src/data_agent/agent/clarifier.py`
- `src/data_agent/agent/sql_checker.py`

当前覆盖：
- `business_rules`：默认中间表、销售额用 `ordered_revenue`、趋势日粒度、月汇总、BR 转化率、ROUND numeric。
- `ask_user_about`：缺时间、广告范围不清、库存口径不清。
- `forbidden_sql`：PII、`GROUP BY month`、BR AVG 转化率。
- `auto_mappings`：Brumate、Belli Welli、Innerbrightness scope token。

### 查询意图与展示策略

目标：SQL 粒度和结果展示一致。

关键文件：
- `src/data_agent/agent/intent.py`
- `src/data_agent/visualization/chart.py`
- `src/data_agent/feishu/webhook.py`
- `src/data_agent/feishu/card_builder.py`

当前意图：
- `trend`：日/时间序列，折线图，最多完整展示 31 行。
- `ranking`：排行，柱状图，默认短表格。
- `comparison`：对比，柱状图，表格最多 20 行。
- `detail`：明细，只展示表格。
- `summary/auto`：汇总或自动判断。

### 高频 SQL 模板

关键文件：
- `src/data_agent/data_catalog/query_templates.md`

当前模板：
- 订单月汇总。
- 订单日趋势。
- Business Report ASIN 排名。
- AMS 排名。
- TACOS 趋势。

---

## 当前待办

### 回归候选审核节奏

目标：让 query log 候选真正进入正式 eval。

建议每周：
1. 运行候选生成。
2. 人工审核 `evals/query_log_regression_candidates.json`。
3. 对确认候选使用 promote 脚本 dry-run。
4. 修正 SQL 后 promote 到正式 eval。
5. 跑 `validate_business_sql_cases.py --execute`。

---

## 维护与运维

### 每周

```bash
# 1. 看成功率、错误率、慢查询
.venv/bin/python scripts/metrics.py --days 7

# 2. 看用户负反馈
.venv/bin/python scripts/review_feedback.py --days 7

# 3. 生成回归候选
.venv/bin/python scripts/generate_regression_candidates.py --days 7

# 4. 跑正式业务回归
.venv/bin/python scripts/validate_business_sql_cases.py --execute
```

### Schema / Catalog 变更时

```bash
# 1. 同步 Catalog metadata
.venv/bin/python scripts/refresh_catalog_metadata.py

# 2. 同步真实列名（PD-3）
.venv/bin/python scripts/build_allowed_columns.py

# 3. 重新生成中间表 scope alias（表范围变化时）
.venv/bin/python scripts/build_scope_aliases.py

# 4. 重新生成本地语义索引（PD-4-lite）
.venv/bin/python scripts/build_table_semantic_index.py
```

### Promote 候选到正式回归

```bash
# dry-run，先看生成的 case
.venv/bin/python scripts/promote_regression_candidate.py \
  --candidate-id <candidate_id> \
  --confirm-reviewed \
  --sql-file /path/to/reviewed.sql

# 真正写入
.venv/bin/python scripts/promote_regression_candidate.py \
  --candidate-id <candidate_id> \
  --confirm-reviewed \
  --confirm \
  --sql-file /path/to/reviewed.sql
```

### 部署

代码、Catalog、模板或规则变更后：

```bash
docker compose up -d --build data-agent
curl --max-time 5 -s http://127.0.0.1:8010/health
```

仅 `.env` 变更时，必须重建/重建容器以重新读取环境变量：

```bash
docker compose up -d --force-recreate data-agent
```

不要只用 `docker compose restart data-agent` 期待 `.env` 生效。

---

## 关键决策记录

1. **中间表是主数据源**：默认只使用 `intermediate_amazon_`，旧 Innerbrightness 专用表不再作为默认路径。
2. **通用销售额默认 `ordered_revenue`**：只有明确 Business Report、sessions、转化率或广告归因时才切换口径。
3. **趋势覆盖月汇总默认规则**：用户说“趋势/走势”时，整月也要按 `report_date` 返回完整日序列。
4. **`GROUP BY month` 禁止**：月汇总用 `GROUP BY 1` 或原表达式。
5. **结构化规则优先沉淀**：新业务规则应优先进入 `rules.json`，再由 prompt、clarifier、checker 消费。
6. **自动修复不绕过校验**：repair 和 LLM retry 生成的 SQL 仍必须经过安全、业务和 schema 校验。
7. **候选不自动进正式 eval**：真实失败先进入候选池，人工确认后 promote。
8. **语义索引只补业务域，不重复选品牌**：品牌/店铺归属由 scope alias 处理；semantic index 用来区分 orders、BR、AMS、DSP、库存、退货等业务域。

---

## 测试矩阵

| 模块 | 测试文件 |
|---|---|
| column selector | `tests/test_column_selector.py` |
| query examples / few-shot | `tests/test_query_examples.py` |
| table semantic index / routing | `tests/test_table_semantic_index.py` |
| SQL checker / schema / business rules | `tests/test_sql_checker.py` |
| SQL repair / executor retry | `tests/test_sql_repair.py`, `tests/test_sql_executor.py` |
| intent / visualization | `tests/test_intent.py`, `tests/test_visualization.py` |
| Feishu card / webhook | `tests/test_feishu_card_builder.py`, `tests/test_feishu_webhook.py` |
| concurrency / query log idempotency | `tests/test_query_log.py`, `tests/test_feishu_webhook.py` |
| structured rules | `tests/test_catalog_rules.py` |
| regression candidates / promote | `tests/test_generate_regression_candidates.py`, `tests/test_promote_regression_candidate.py` |
| business SQL eval runner | `tests/test_business_sql_regression.py` |
| **当前全量** | **153 passed** |
