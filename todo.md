# 项目理解与推进规则确认

---

# Scope 品牌过滤误用修复计划

## Spec

目标：修复历史查询 `0da354def31c43d8900438bc58a08e93` 暴露的问题：SQL 在已经选中 `intermediate_amazon_..._blueland_view` 的情况下，又生成 `brand = 'blueland'`，导致大小写敏感不匹配或冗余过滤。需要把字段值枚举得到的真实取值启发沉淀为规则和机械修复。

边界：
- 不删除用户明确给出的非 scope 字段过滤。
- 只修复中间表 scope token/alias 与 `brand/customer/customer_name/profile_name` 的重复过滤。
- 字符串过滤如果确需保留，优先使用 `LOWER(field) = LOWER('<value>')`；但 scope 表上的同 scope 过滤应直接移除。
- 保持 SQL repair 幂等，并补充回归测试。

## Checklist

- [x] 定位当前 prompt/catalog/rules 对 brand scope 过滤的约束
- [x] 增加 scope 字符串过滤机械修复
- [x] 补强模板/系统规则
- [x] 补充回归测试覆盖用户 SQL
- [x] 运行验证并提交 push

## Review

- 当前 Catalog 已有“不要猜 brand/customer = scope token”的业务规则，但历史 SQL 说明 prompt 约束不足，需要执行前 repair 兜底。
- `sql_repair.py` 已新增 `remove_redundant_scope_identity_filter`：从中间表名解析 scope token，并结合 `scope_aliases.json` 删除 `brand/customer/customer_name/profile_name = '<scope token or alias>'` 这类重复过滤。
- 系统 prompt 已补充：scope 表上不要添加同 scope 的 `brand/customer/customer_name/profile_name` 过滤；如果确需按字段真实值过滤，使用 `LOWER(field) = LOWER('<value>')`。
- 已用用户查询 `0da354def31c43d8900438bc58a08e93` 验证：repair 移除 `brand = 'blueland'`，保留 `LOWER(ams_type) IN ('sp', 'sd', 'sb')`，实际执行返回 5 行。
- 回归测试已覆盖完整用户 SQL、`LOWER(customer) = LOWER(scope alias)` 移除、非 scope 身份过滤保留。
- 验证通过：相关测试 36 passed；全量测试 159 passed；业务 SQL 回归 13 passed。
- 已提交并推送：`cc923d7 Repair redundant scope identity filters`。

---

# 中间表字段值枚举画像计划

## Spec

目标：对 `intermediate_amazon_` 开头的中间表做结构画像，帮助理解表类型、共性字段、品牌/店铺差异字段和低基数字段取值。先统计主要表类型和字段分布，再对适合枚举的字段查询 distinct/top values。

边界：
- 不枚举 ASIN、SKU、订单号、campaign id、keyword text 等高基数或敏感明细字段。
- 只使用中间表，不回退旧表。
- 查询要限制样本、超时和 distinct 阈值，避免拖垮数据库。
- 输出为文档和机器可读 JSON，后续可用于丰富 Data Catalog。

## Checklist

- [x] 确认现有 Catalog、数据库连接和中间表覆盖范围
- [x] 设计低基数字段枚举策略和排除规则
- [x] 执行数据库采样/聚合查询并生成画像文档
- [x] 验证脚本和结果，更新 Catalog 后续建议
- [x] 提交并 push

## Review

- 已确认当前账号可 SELECT 的 `intermediate_amazon_` 对象为 462 张，全部来自中间表层。
- 主类型统计：`dsp` 160、`ams_advertised_product` 46、`orders` 35、`ams_campaigns` 35、`business_report` 34、`ams_search_terms` 34、`ams_placement` 32、`ams_targeting` 29、`ads_audience_campaign` 25、`1p_orders` 18、`returns` 8、`amazon_intermediate` 5、`inventory_days` 1。
- 新增 `scripts/profile_intermediate_field_values.py`：全量统计字段结构；字段值只采样低基数维度字段；排除 ASIN、SKU、ID、name、search term、targeting text、URL 等高基数明细。
- 已生成 `docs/intermediate_amazon_field_values.md` 和 `docs/intermediate_amazon_field_values.json`。
- 结构统计覆盖 462 张表；值枚举对 19 张代表表、114 个字段执行采样，73 个字段成功返回枚举值，36 个字段因视图较慢记录为 timeout，5 个字段无值。
- 已确认枚举结果没有导出 ASIN/SKU/search term 这类字段值。
- 发现的结构启发：`brand/year/month/quarter/model/report_date/customer/profile_name/report_type` 是跨域高频字段；订单表的核心指标字段是 `ordered_revenue/ordered_units/order_items`；Business Report 核心流量字段集中在 `trafficbyasin_*`；AMS 通用指标集中在 `ams_spend/ams_sales/ams_click/ams_impression/ams_orders`；DSP 有统一的 `dsp_*` 指标族但域内字段变体最多。
- 品牌/店铺差异上，`orders` 中 `vp_us_weekly_state` 有 `state/week_key`，`ams_placement` 中 `philips_dashboard_m` 是明显非标准字段集合，`amazon_intermediate` 的 Philips/AMS time 表结构也明显偏特例。
- 后续 Catalog 建议：把 `brand/customer/customer_name` 的真实枚举差异沉淀到 scope aliases；把 `ams_type/ad_type/ads_type/report_type/campaign_type/placement_classification/status/reason` 作为可提示的过滤字段；DSP 和 1P 值枚举需要单独更保守的慢查询方案。
- 验证通过：新增测试 3 passed；全量测试 156 passed；业务 SQL 回归 13 passed。
- 已提交并推送：`86e495e Profile intermediate field values`。

---

# 冗余文件清理计划

## Spec

目标：清理仓库中的冗余文件、未使用文件和本地生成物，保持 GitHub 仓库轻量，同时不误删运行所需 Catalog、测试数据或项目文档。

边界：
- 优先删除明确的本地生成物、缓存、大型数据库 inventory 导出和无内容临时文件。
- 对已跟踪文件必须先做引用搜索或用途判断，不能仅凭文件名删除。
- 清理后运行测试验证；必要时同步提交并 push。

## Checklist

- [x] 检查 Git 状态、未跟踪文件、忽略文件和大文件
- [x] 审计已跟踪文件引用关系
- [x] 删除明确冗余文件和本地生成物
- [x] 运行测试验证
- [x] 提交并 push 清理结果

## Review

- 初步发现 `Untitled.txt` 为未跟踪临时文件。
- 初步发现 `docs/database_inventory.json` 和 `docs/database_inventory.md` 是已被 `.gitignore` 排除的大型生成物，仍留在本地磁盘。
- 初步发现多处 `__pycache__` 和 `.pytest_cache`，均为可删除缓存。
- 已删除本地 `Untitled.txt`、`docs/database_inventory.json`、`docs/database_inventory.md`、`__pycache__` 和 `.pytest_cache`。
- 已删除已跟踪的空反馈报告生成物 `docs/feedback_review.md`；该文件可由 `scripts/review_feedback.py` 按需重新生成。
- 已更新 `.gitignore`，防止 `Untitled*.txt` 和 `docs/feedback_review.md` 再次进入版本控制。
- 已确认运行时 Catalog 大文件 `tables_columns.json` 和 `table_semantic_index.json` 被代码和测试读取，保留。
- Secret pattern 扫描未发现可提交文件中存在真实密钥值；只命中 `.env.example` 空占位、代码提示和文档变量名。
- 验证通过：全量测试 153 passed，业务 SQL 回归 13 passed。
- 已提交并推送：`9618c85 Clean generated and local files`。

---

# 架构整理与 GitHub 首次发布计划

## Spec

目标：整理项目入口架构说明，初始化 Git 仓库，确认敏感文件不进入版本控制，并将项目 push 到 GitHub 仓库。

边界：
- 不移动核心代码目录，避免引入不必要风险。
- 不提交 `.env`、`postgresql.env`、`storage/`、本地 IDE 配置、虚拟环境或缓存。
- push 前必须运行全量测试和业务 SQL 回归。

## Checklist

- [x] 检查当前 Git 状态和远程配置
- [x] 更新 `.gitignore`
- [x] 重整 README 架构说明
- [x] 恢复项目计划书文档
- [x] 运行全量测试和业务 SQL 回归
- [x] 初始化 Git 并提交
- [x] 创建/连接 GitHub 仓库并 push

## Review

- 当前目录原本不是 Git 仓库，已确认需要首次初始化。
- `.gitignore` 已补充 `postgresql.env` 和 `.claude/settings.local.json`，并继续排除 `.env`、`.venv/`、`storage/`、缓存文件。
- README 已重写为当前 Data Detector 架构说明，覆盖 progressive disclosure、安全、并发、目录结构、配置、运行和验证命令。
- `Data Detector项目计划书.md` 已恢复到根目录。
- 验证通过：全量测试 153 passed，业务 SQL 回归 13 passed。
- 已创建 GitHub 私有仓库 `ecoyoung/data_agent`，本地 `main` 已跟踪 `origin/main`。
- 大型生成物 `docs/database_inventory.json` 和 `docs/database_inventory.md` 已排除，不进入首次提交。

---

# Blueland SP+SD 广告 ASIN 空结果修复计划

## Spec

目标：修复用户问题“blueland 2026-07-13 每个产品asin的sp+sd广告花费和销售额”返回空结果的问题。真实数据存在，空结果来自 SQL 错误过滤：`brand = 'blueland'` 与实际 `brand = 'Blueland'` 大小写敏感不匹配，且 SQL 漏掉 `SP+SD` 对应的 `ams_type` 过滤。

边界：
- 不改变广告指标口径：花费用 `ams_spend`，广告销售用 `ams_sales`。
- 不改变选表：产品 ASIN 粒度广告表现继续使用 `intermediate_amazon_ams_advertised_product_<scope>_view`。
- 修复应沉淀为 Catalog/Prompt 规则和测试，不只手工给一条 SQL。

## Checklist

- [x] 记录 lessons
- [x] 修正表级 prompt 过滤展示，避免展示空字符串默认过滤
- [x] 增加品牌 scope 后缀与 brand/customer 过滤规则
- [x] 增加 AMS 类型过滤规则，SP/SD/SB 使用 `ams_type`
- [x] 修复 SQL checker 对 `FILTER` 关键字误判
- [x] 补充回归测试
- [x] 运行验证并重建服务

## Review

- 已确认真实数据存在：`intermediate_amazon_ams_advertised_product_blueland_view` 在 `2026-07-13` 有 SP 700 行、SD 45 行；合计 SP+SD 按 ASIN 汇总返回 41 行，总广告花费 20131.38，总广告销售额 43407.68。
- 空结果根因是 SQL 使用 `brand = 'blueland'`，但实际值是 `Blueland`，大小写敏感导致过滤为空；同时用户问 `sp+sd`，SQL 漏掉 `LOWER(ams_type) IN ('sp', 'sd')`。
- `scripts/build_intermediate_catalog.py` 已更新业务规则：表名 scope 已限定品牌/店铺，不要再猜 `brand/customer = scope token`；SP/SD/SB 必须使用真实广告类型字段，`ams_advertised_product_*` 使用 `ams_type`。
- `prompt_builder.py` 已修正表级过滤展示：只展示有确定默认值的过滤条件；`brand/customer` 这类没有默认值的字段显示为可选过滤字段，并提示不要猜值。
- `column_selector.py` 已增加广告类型列选择：用户提到 SP/SD/SB 时自动暴露 `ams_type/ads_type/ad_type/report_type` 中存在的字段。
- `query_templates.md` 已新增 “AMS advertised ASIN 按广告类型汇总”模板，明确用 `advertised_asin`、`ams_spend`、`ams_sales`、`LOWER(ams_type) IN (...)`，不要猜 `brand='<scope>'`。
- `sql_checker.py` 已把 PostgreSQL `FILTER` 加入非列关键字，避免 `COUNT(*) FILTER (...)` 被裸列校验误判。
- 已重新生成 Catalog 与 semantic index。
- 相关测试通过：`tests/test_column_selector.py tests/test_catalog.py tests/test_sql_checker.py` 44 passed。
- 业务 SQL 回归实际执行通过：13 passed，0 failed。
- 全量测试通过：153 passed，2 个上游 warning。
- Docker 已重建启动，`/health` 返回 ok；容器内 smoke 确认正确 SQL 返回 41 行。

---

# text 日期字段与 DATE literal 比较报错修复计划

## Spec

目标：修复 query `ac8d76f00aae4e2cbafec50e276c114f` 中 `intermediate_amazon_ams_advertised_product_blueland_view.report_date` 为 text，却生成 `report_date = DATE '2026-07-13'` 导致 PostgreSQL 报 `operator does not exist: text = date` 的问题。

边界：
- 不改变业务口径和选表逻辑。
- 仅对 Catalog 中日期字段类型为 text/character 的表做执行前机械修复。
- 修复应覆盖带表别名和不带表别名的 `report_date` 日期比较。
- 同步修正 Catalog 生成脚本中的 `date_cast_hint`，减少 LLM 继续生成错误 SQL。

## Checklist

- [x] 记录 lessons
- [x] 增加 text 日期字段 SQL repair
- [x] 修正 Catalog 生成脚本 date cast hint
- [x] 补充回归测试
- [x] 运行相关测试和业务回归
- [x] 重建服务并做 smoke

## Review

- 已定位 query `ac8d76f00aae4e2cbafec50e276c114f`：用户问 `sp+sb汇总`，LLM 生成 SQL 访问 `intermediate_amazon_ams_advertised_product_blueland_view`，该表 `report_date` 类型为 `text`，原 SQL 使用 `report_date = DATE '2026-07-13'` 导致 PostgreSQL `operator does not exist: text = date`。
- `sql_repair.py` 已新增 text 日期字段机械修复：当 SQL 引用了 Catalog 中 `report_date` 类型为 text/character 的表时，将裸 `report_date` 与 `DATE` literal 的 `= / >= / <= / < / > / IN / BETWEEN` 比较改为 `report_date::date ...`。
- `scripts/build_intermediate_catalog.py` 已修正 `date_cast_hint`：text 日期字段提示为 `report_date::date（原字段类型为 text，与 DATE literal 比较时必须 cast）`。
- 已重新生成 `tables_metadata.json`、`tables_columns.json`、`allowed_columns.json`，均覆盖 462 张表；已同步重建 `table_semantic_index.json`。
- 同一 SQL 继续暴露出裸列幻觉：该表没有 `country` 和 `campaign_type`，实际可用 `country_code` 和 `ams_type`。`sql_checker.py` 已增加单表无 CTE 场景下的裸列存在性校验，提前拦截 `country/campaign_type` 这类字段幻觉。
- `webhook.py` 已修正 LLM retry 失败时的错误展示：现在会追加“重试 SQL 仍出错”的真实错误，避免只暴露首次数据库错误。
- 新增/扩展测试覆盖 text 日期修复、qualified/unqualified 日期比较、单表裸列幻觉、retry 失败错误展示。
- 相关测试通过：`tests/test_sql_repair.py tests/test_sql_checker.py tests/test_sql_executor.py tests/test_feishu_webhook.py` 59 passed。
- 业务 SQL 回归实际执行通过：13 passed，0 failed。
- 全量测试通过：150 passed，2 个上游 warning。
- Docker 已重建启动，`/health` 返回 ok；容器内 smoke 确认原始 SQL 不再触发数据库 text=date 报错，而是在业务校验阶段提示不存在列 `campaign_type, country`；字段修正为 `country_code/ams_type` 后真实执行成功，返回 41 行。

---

# Data Detector 项目计划书重写计划

## Spec

目标：在保留 `Data Detector项目计划书.md` 原有大框架的前提下，按四周周期重写内容；从 0 开始描述整个项目，不按当前实际进度倒推。计划需符合三人小团队资源现实，明确目标、范围、阶段、交付物、分工、风险、验收指标和后续路线。

边界：
- 只更新项目计划书文档，不改代码。
- 不泄露数据库账号、密钥、客户敏感数据。
- 不把已经完成的实现当作前提；以“新项目启动计划”的口径来写。
- 风格偏正式，可直接用于内部评审/立项沟通。

## Checklist

- [x] 保留原文档大框架并重写项目计划书
- [x] 明确三人团队分工和资源约束
- [x] 补充从 0 到试点/生产化的四周阶段计划
- [x] 补充风险、验收标准、治理机制
- [x] 做文档基础校验

## Review

- 已重写 `Data Detector项目计划书.md`，保留原有大框架：引言、项目理解、项目团队、月度目标、任务排期、关键交付物、风险与缓解、后续路线。
- 文档口径已调整为“从 0 启动四周 MVP 项目”，不再把当前已有实现、测试数量或中间表进度写成既有基础。
- 四周计划已明确：
  - Week 1：项目启动与最小查询闭环。
  - Week 2：Data Catalog、指标口径与准确率基础。
  - Week 3：可靠性、并发、安全与用户体验。
  - Week 4：试点准备、验收与交接。
- 已补充三人团队分工、资源约束、MVP 包含/不包含范围、量化验收指标、交付物清单、风险缓解和后续路线。
- 基础校验通过：文档包含 Week 1-4、M1-M4；未包含当前测试数量、当前已完成实现或 `intermediate_amazon_` 等现有进度细节。

---

# Per-session 串行化计划

## Spec

目标：同一个会话/session 内只允许一个查询同时执行，避免用户连续追问或飞书并发投递时，第二个问题读取到半更新上下文，或两条结果交叉写入历史。

边界：
- 第一阶段不引入后台队列；同一 session 已有查询运行时，后续请求快速返回 busy。
- 不影响不同 session 的并发能力，仍受全局 `MAX_CONCURRENT_QUERIES` 限制。
- 不改变 SQL 业务口径、Catalog、飞书卡片展示结构。

## Checklist

- [x] 增加 session 级互斥锁/信号量
- [x] 同 session busy 时更新 query log 并返回提示卡片
- [x] 保证 global semaphore 和 session semaphore 正确释放
- [x] 增加 per-session 并发测试
- [x] 更新并发架构文档
- [x] 运行测试、业务回归、全量测试和健康检查

## Review

- `feishu/webhook.py` 新增 session 级 `BoundedSemaphore(1)`，同一 session 已有查询运行时，后续请求快速返回 busy，不进入 `_handle_user_query()`。
- session busy 会更新 query log：`status=error`，`error=session busy: previous query is still running`。
- global semaphore 与 session semaphore 分层处理：先抢 session，再抢 global；global busy 时会释放 session，正常/异常路径都会释放两个 semaphore。
- 不同 session 不受 session 锁影响，仍可并行，受 `MAX_CONCURRENT_QUERIES` 总量限制。
- 新增测试覆盖同 session busy、不同 session 可继续执行。
- 已更新 `docs/concurrency_architecture.md`，将 Session 级互斥记录为已完成能力，并明确当前是快速失败，不是排队。
- 相关测试通过：`tests/test_feishu_webhook.py tests/test_query_log.py` 23 passed。
- 业务 SQL 回归实际执行通过：13 passed，0 failed。
- 全量测试通过：144 passed，2 个上游 warning。
- Docker 已重建启动，`/health` 返回 ok；容器内 smoke 确认同一 session semaphore 第一次获取成功、第二次并发获取失败。

---

# 并发与上线前架构加固计划

## Spec

目标：在进入真实用户测试前，先补齐当前单机服务的并发安全基础，降低飞书重复投递、同一会话并发请求、SQLite 写冲突、同步慢调用阻塞 FastAPI 事件循环带来的风险。

边界：
- 第一阶段只做单机/单容器内的并发加固，不引入 Redis、Celery、Postgres 作业队列等新基础设施。
- 不改变 SQL 业务口径、Catalog、数据权限和飞书卡片业务内容。
- 保持当前同步 LLM/SQL 生成链路，但从 async webhook 中挪到线程池执行。
- 幂等必须持久化到 SQLite，不能只依赖进程内 set。

## Checklist

- [x] 增加持久化消息幂等 claim，处理飞书重复投递
- [x] 给会话历史管理增加线程锁
- [x] 将 webhook 慢处理链路移到线程池，避免阻塞事件循环
- [x] 增加查询并发上限
- [x] 增加并发与重复消息测试
- [x] 运行相关测试、业务回归、全量测试和健康检查
- [x] 更新架构文档与 Review

## Review

- 新增 `message_event_claims` SQLite 表和 `claim_message_query_event()`，用 `message_id` 原子 claim 飞书消息；重复投递直接返回，不再二次调用 LLM/SQL。
- `feishu_webhook()` 已将慢处理链路通过 `run_in_threadpool()` 执行，避免同步 LLM、SQL、飞书发卡片阻塞 FastAPI event loop。
- `session/manager.py` 已给进程内会话历史增加 `RLock`，保护历史读写、清空和过期清理。
- 新增 `MAX_CONCURRENT_QUERIES` 配置，默认 4；超过并发上限时快速返回 busy 卡片，并写入 query log error。
- 新增 `docs/concurrency_architecture.md`，记录当前单机并发模型、已解决问题和下一阶段队列/Redis/多副本方向。
- 新增测试覆盖：SQLite 消息 claim 幂等、webhook 重复 `message_id` 不重复处理、并发上限满载时不进入查询链路。
- 相关测试通过：`tests/test_query_log.py tests/test_feishu_webhook.py` 21 passed。
- 业务 SQL 回归实际执行通过：13 passed，0 failed。
- 全量测试通过：142 passed，2 个上游 warning。
- Docker 已重建启动，`/health` 返回 ok；容器内 smoke 确认 `MAX_CONCURRENT_QUERIES=4`，同一 `message_id` 第一次 claim 成功、第二次 claim 返回重复；smoke query log 已清理。

---

# PD-4-lite 本地语义检索增强计划

## Spec

目标：在不引入外部 embedding 服务的前提下，先完成 PD-4 的轻量落地：从现有 `tables_metadata.json`、`tables_columns.json` 和 scope alias 生成本地语义 token 索引，并作为 `_score_table` 的补充分，增强“营收 / GMV / 购物车 / 转化”等长尾问法的表路由稳定性。

边界：
- 不替换现有关键词、scope alias、domain hints 规则，只做加权补充。
- 不改变 SQL 生成口径：通用销售额仍默认 `ordered_revenue`；BR 只在明确 Business Report / sessions / traffic / conversion 时使用。
- 索引离线生成，运行时只读 JSON，不调用外部服务。
- 索引体积需要可控，避免把全部列描述原文塞进 prompt。

## Checklist

- [x] 新增本地语义索引生成脚本
- [x] 生成 `table_semantic_index.json`
- [x] 在 `prompt_builder._score_table` 接入语义补充分
- [x] 补充路由与索引测试
- [x] 更新 `docs/progressive_disclosure.md` 与维护命令
- [x] 运行业务回归、全量测试和服务健康检查

## Review

- 新增 `scripts/build_table_semantic_index.py`，从 `tables_metadata.json`、`tables_columns.json` 和 `scope_aliases.json` 生成本地轻量 semantic token 索引。
- 新增 `src/data_agent/data_catalog/table_semantic_index.json`，当前覆盖 462 张 `intermediate_amazon_` 中间表，每张表最多保留 90 个高权重 token。
- `prompt_builder._score_table` 已接入 `_semantic_score_table()`，语义分作为 capped supplemental score，不替换已有关键词、scope alias、domain hints。
- 已修正索引策略：scope/品牌 alias 不在 semantic index 中重复高权重加分，避免同品牌所有表一起被抬高；品牌选择仍由专用 scope alias 处理。
- 已补充泛销售硬规则：`销售额/营收/收入/GMV/revenue` 在未明确 Business Report、sessions、流量、转化、购物车时，继续偏向 `intermediate_amazon_3p_orders_*_view`。
- 新增 `tests/test_table_semantic_index.py`，覆盖 tokenizer、索引字段、scope alias 不重复加权、GMV 路由到 orders、购物车长尾路由到 Business Report。
- 已更新 `docs/progressive_disclosure.md`，将 PD-4-lite 记录为已完成能力，并补充 schema/catalog 变更时重建 semantic index 的维护命令。
- 相关测试通过：`tests/test_table_semantic_index.py tests/test_catalog.py` 13 passed。
- JSON 校验通过：`table_semantic_index.json`、`tables_metadata.json`、`tables_columns.json` 均覆盖 462 张表，`scope_aliases.json` 覆盖 94 个 scope。
- 业务 SQL 回归实际执行通过：13 passed，0 failed。
- 全量测试通过：139 passed，2 个上游 warning。
- Docker 已重建启动，`/health` 返回 ok；容器内 smoke 确认 semantic index 读取为 462 张表，`Brumate 2026年6月 GMV 趋势` 路由到 orders，`Brumate 2026年6月为什么用户不点进购物车` 路由到 Business Report。

---

# Progressive Disclosure 文档校准计划

## Spec

目标：更新 `docs/progressive_disclosure.md`，同步当前已经完成的意图层、结构化规则、SQL repair/LLM retry、query log 候选生成与 promote 工具，修正过时的 TODO、测试数量、维护命令和部署说明。

边界：
- 只更新文档，不改运行逻辑。
- 保留原有渐进式披露架构说明，但补充当前实际链路。
- 明确哪些事项已完成、哪些仍是下一步。

## Checklist

- [x] 更新架构总览和完成状态
- [x] 将 PD-6、PD-7 从 TODO 移到已完成/部分完成
- [x] 补充结构化规则、intent、模板和回归闭环
- [x] 修正维护命令、部署说明和测试数量
- [x] 运行文档/JSON 基础验证

## Review

- 已重写 `docs/progressive_disclosure.md` 为当前状态版：架构总览新增 Intent、Rules、Repair、Checker、Retry 和展示策略。
- 已将 PD-6 自动修复与单次重试、PD-7 离线评估与回归闭环移入已完成能力，并补充对应文件：`sql_repair.py`、`generate_regression_candidates.py`、`promote_regression_candidate.py` 等。
- 已补充结构化规则层、查询意图与展示策略、高频 SQL 模板、候选生成与 promote 闭环。
- 已修正维护命令：每周 metrics / feedback / candidates / business eval；schema 变更同步 metadata、allowed columns、scope aliases。
- 已修正部署说明：代码/Catalog/规则变更使用 `docker compose up -d --build data-agent`；`.env` 变更使用 `--force-recreate`，不要只 restart。
- 已修正测试矩阵为当前 `135 passed`。
- 基础验证通过：`rg` 确认文档包含 PD-6/PD-7、structured rules、候选生成、promote、build 部署说明，且不再保留旧的 `106 passed` 或过时索引脚本文案。

---

# 回归候选 Promote 工具计划

## Spec

目标：新增半自动审核/合并工具，将 `evals/query_log_regression_candidates.json` 中已人工确认的候选安全追加到正式业务 SQL 回归集 `evals/innerbrightness_business_questions.json`。

边界：
- 默认 dry-run，只预览不写文件。
- 必须显式 `--confirm` 才写入。
- 对 `needs_human_review=true` 的候选，必须额外显式 `--confirm-reviewed`。
- 写入前校验 SQL 安全、业务规则、expected tables、required/forbidden terms。
- 去重：同一 candidate/source_query_id/case id 不重复 promote。

## Checklist

- [x] 新增 promote 脚本
- [x] 支持 dry-run / confirm / reviewed gate
- [x] 支持 case id、SQL、required/forbidden terms override
- [x] promote 后更新候选 promoted 状态
- [x] 增加脚本单测
- [x] 运行验证

## Review

- 新增 `scripts/promote_regression_candidate.py`，支持将 `query_log_regression_candidates.json` 中的单条候选提升为正式 eval case。
- 默认 dry-run；必须 `--confirm` 才写入。候选若 `needs_human_review=true`，还必须传 `--confirm-reviewed`。
- 支持 `--case-id`、`--sql`、`--sql-file`、重复 `--required-term`、重复 `--forbidden-term`。已修正 term 参数行为，避免把 `to_char(report_date, 'YYYY-MM')` 内部逗号误拆。
- promote 写入前会校验 SQL 安全、业务规则、日期过滤、expected tables、required/forbidden terms，并检查 case id、source candidate、source query 去重。
- promote 成功后会追加正式 eval，并把候选标记为 `promoted=true`、`promoted_at`、`promoted_case_id`、`needs_human_review=false`。
- 新增 `tests/test_promote_regression_candidate.py`，覆盖 case 构建、review gate、dry-run、confirm 写入、重复 source query 拦截和 SQL 函数逗号 term 保留。
- 已实际 dry-run：未确认 review 时被拦截；确认 review 但候选 SQL 仍错误时被校验拦截；传入人工修正 SQL 后 dry-run ok。未写入正式 eval。
- 验证通过：promote/candidate 脚本测试 11 passed；JSON 校验通过；业务 SQL 回归实际执行 13 passed；全量测试 135 passed，2 个上游 warning。

---

# Query Log 回归候选自动生成计划

## Spec

目标：从真实 `query_logs.sqlite3` 自动生成可审查的回归候选 JSON，将失败查询、LLM 修复重试、用户负反馈沉淀为测试资产候选，避免同类线上问题反复出现。

边界：
- 不自动修改正式 `evals/innerbrightness_business_questions.json`。
- 输出候选文件供人工审核：`evals/query_log_regression_candidates.json`。
- 不输出敏感配置、账号、密码、token；仅使用 query log 中已有的用户问题、SQL、错误和反馈。
- 候选只做启发式提取，不能替代人工确认业务口径。

## Checklist

- [x] 新增候选生成脚本
- [x] 支持失败、负反馈、SQL repair attempt 三类来源
- [x] 自动提取表名、required_terms、forbidden_terms 初稿
- [x] 增加脚本单测
- [x] 实际运行生成候选文件
- [x] 运行测试和验证

## Review

- 新增 `scripts/generate_regression_candidates.py`，从 `query_events` 和 `feedback_events` 生成可审查回归候选。
- 支持来源：`query_error`、`negative_feedback`、`sql_repair_attempt`；支持 `--days`、`--all-time`、`--no-success-repairs`、`--output`。
- 候选字段包括：原问题、状态、错误、SQL、涉及表、推荐 required terms、推荐 forbidden terms、反馈、行数、列、Catalog docs、人工审核标记。
- 新增 `tests/test_generate_regression_candidates.py`，覆盖 CTE 表名过滤、term 推断、负反馈候选和临时 SQLite 生成。
- 已实际运行 `.venv/bin/python scripts/generate_regression_candidates.py --days 30`，生成 `evals/query_log_regression_candidates.json`，当前 10 条候选。
- 验证通过：候选 JSON 格式校验通过；候选脚本相关测试 7 passed；业务 SQL 回归实际执行 13 passed；全量测试 128 passed，2 个上游 warning。

---

# Data Catalog Rules 结构化计划

## Spec

目标：把当前散落在 prompt、metric catalog、clarifier、SQL checker 中的业务规则收敛到机器可读 `rules.json`。规则分为 `business_rule`、`ask_user_about`、`auto_mapping`、`forbidden_sql`，并由 prompt、clarifier、SQL checker 共用，避免同一规则多处手写后漂移。

边界：
- 不删除现有 Markdown 文档；先让结构化规则成为共享来源和 prompt 补充层。
- 保持现有行为不回退：销售额默认 `ordered_revenue`、趋势日粒度、月汇总 `GROUP BY 1`、BR 转化率禁 AVG、PII 禁查、缺时间追问等。
- 结构化规则先覆盖当前已验证的高频规则，不一次性抽象所有 Catalog 内容。

## Checklist

- [x] 新增 `rules.json`
- [x] 增加规则加载器和 prompt 渲染
- [x] clarifier 使用结构化追问规则
- [x] SQL checker 使用结构化 forbidden/sql rule
- [x] 增加规则加载、prompt、clarifier、checker 测试
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 新增 `src/data_agent/data_catalog/rules.json`，当前结构化覆盖 6 条 `business_rules`、3 条 `ask_user_about`、3 条 `forbidden_sql` 和 3 条 `auto_mappings`。
- 新增 `load_catalog_rules()` 与 `render_catalog_rules_for_prompt()`，Prompt 现在会注入 `Data Catalog: structured rules`，让 LLM 看到机器可读规则层。
- `clarifier.py` 已从结构化规则读取缺时间、广告范围、库存范围的关键词和追问文案；现有产品 ASIN/SKU 追问逻辑保留为代码规则。
- `sql_checker.py` 已从结构化 `forbidden_sql` 读取 PII、`GROUP BY month`、Business Report AVG 转化率等禁用规则；原专用函数保留作兜底。
- 新增 `tests/test_catalog_rules.py`，并扩展 Catalog/Clarifier/SQL checker 测试，覆盖规则加载、prompt 注入、PII forbidden rule 等。
- 验证通过：相关测试 44 passed；业务 SQL 回归实际执行 13 passed；全量测试 124 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认结构化规则加载、prompt 注入和 PII SQL 拦截均生效。

---

# SQL 自动修复与单次重试计划

## Spec

目标：在 SQL 执行前后增加稳定修复层。执行前做确定性机械修复；如果仍因业务校验或数据库错误失败，则把用户问题、原 SQL、错误信息、意图和模板上下文交给 LLM 只重写 SQL 一次，再走同一套安全/业务校验和执行。

边界：
- 所有修复后的 SQL 仍必须经过 `validate_sql`、`validate_business_sql` 和只读数据库连接。
- 自动机械修复只处理确定性低风险问题：`ROUND(..., n)` numeric cast、月度 `GROUP BY month` 改 `GROUP BY 1`。
- LLM 重试最多一次，避免循环。
- 不吞掉错误；重试失败时返回原始错误和最终 SQL。

## Checklist

- [x] 新增 SQL repair 模块
- [x] 执行前接入机械修复
- [x] webhook 接入 LLM 单次重写重试
- [x] 增加修复和重试测试
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 新增 `src/data_agent/agent/sql_repair.py`，统一执行前确定性修复：`ROUND(expr, n)` 自动补 `::numeric`，月度 `to_char(report_date, 'YYYY-MM') AS month` 的 `GROUP BY month` / `ORDER BY month` 自动改为 `GROUP BY 1` / `ORDER BY 1`。
- `sql_executor.execute_query()` 已接入 `repair_sql()`，修复后的 SQL 仍走 `validate_sql`、`validate_business_sql` 和只读数据库连接。
- `webhook._handle_user_query()` 已接入单次 LLM 重试：首次执行失败后，带用户问题、失败 SQL、错误信息和 Catalog 上下文要求 LLM 只输出修正 SQL；重试 SQL 仍走同一套 `execute_query()`。
- 重试最多一次；重试失败不会吞错，仍返回错误卡片并记录原始响应与修复尝试。
- 新增 `tests/test_sql_repair.py`，并扩展 SQL executor / Feishu webhook 测试，覆盖机械修复、业务校验前修复、失败后重试成功。
- 验证通过：相关测试 48 passed；业务 SQL 回归实际执行 13 passed；全量测试 121 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认 `ROUND` numeric cast 和 `GROUP BY month` 修复均生效。

---

# 查询意图层、展示策略与高频模板固化计划

## Spec

目标：把当前靠 prompt 和零散展示判断的行为收敛成统一规则：先识别问题意图（趋势、汇总、排行、对比、明细），再决定 SQL 粒度提示和结果展示策略；同时固化高频 Amazon SQL 模板，减少 LLM 临场拼错。

边界：
- 不引入新服务或外部依赖。
- 不替换现有 LLM 生成链路，只在 prompt 前置意图提示、展示层统一策略。
- 保持现有中间表主数据源和安全校验不变。
- 高频模板先覆盖当前高频：订单月汇总、订单日趋势、BR ASIN 排名、AMS 排名、TACOS 趋势/汇总。

## Checklist

- [x] 新增轻量查询意图识别模块
- [x] 将意图提示注入 SQL prompt
- [x] 用意图层统一飞书图表类型和表格展示上限
- [x] 新增高频 SQL 模板文档并注入 prompt
- [x] 增加单测和业务回归
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 新增 `src/data_agent/agent/intent.py`：轻量识别 `trend/ranking/comparison/detail/summary/auto`，统一给出图表类型、表格展示上限和 SQL 粒度提示。
- `prompt_builder.py` 已注入 `# ===== Query Intent =====`，LLM 生成 SQL 前能看到当前问题的意图、推荐图表和粒度提示。
- 飞书展示层已改为使用意图策略：趋势优先折线图并展示最多 31 行，排行/对比走柱状图，明细类跳过图表并展示表格。
- 新增 `src/data_agent/data_catalog/query_templates.md` 并注入 prompt，覆盖订单月汇总、订单日趋势、Business Report ASIN 排名、AMS 排名、TACOS 趋势等高频模板。
- 新增 `tests/test_intent.py`，并扩展 Catalog/Feishu 测试，覆盖趋势 prompt 模板、排行意图、明细不画图等行为。
- 验证通过：相关测试 42 passed；业务 SQL 回归实际执行 13 passed；全量测试 117 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认趋势识别为 `trend/line/31`，排行识别为 `ranking/bar/10`，prompt 已包含 intent 和高频模板。

---

# 趋势查询折线图与完整日数据展示修复计划

## Spec

目标：修复 `Brumate 2026年6月份订单销售额趋势` 的展示问题。该问题语义上要求 2026-06 每天一条、完整 30 天数据，并用趋势折线图展示；不能按月汇总成一行，也不能在飞书卡片中只展示前 10 行。

边界：
- 不改变数据库数据。
- “趋势/走势/每日趋势”默认按日期字段日粒度分组；普通“6月份销售额数据”仍可月汇总一行。
- 普通排行榜/Top N 仍保持短表格展示；仅日趋势类结果提高表格展示上限，避免卡片过长。

## Checklist

- [x] 记录 lessons，沉淀“趋势=日粒度折线图完整展示”规则
- [x] 更新 Prompt/Catalog 文案，明确“趋势”覆盖月汇总默认规则
- [x] 飞书结果展示按趋势选择折线图
- [x] 日趋势表格完整展示 30/31 天数据
- [x] 增加 Brumate 2026-06 趋势 SQL 回归和展示测试
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 已从 `storage/query_logs.sqlite3` 确认最近的 `Brumate 2026年6月份订单销售额趋势` SQL 实际返回 `row_count=30`，SQL 本身是日粒度：`report_date` + `SUM(ordered_revenue)` + `GROUP BY report_date`。
- 根因在展示层：webhook 始终生成柱状图，未使用已有折线图函数；飞书卡片表格默认 `max_rows=10`，导致 30 天数据只展示前 10 行。
- 已更新规则：用户说“趋势/走势”时，即使时间是“6月份”，也按 `report_date` 日粒度返回完整日期序列，不走月汇总一行。
- 已接入折线图：趋势或日期轴结果使用 `generate_line_chart()`；普通排行/分类对比仍使用柱状图。
- 已将日趋势表格展示上限提高到 31 行，覆盖自然月 30/31 天，避免只展示前 10 天。
- 已新增 Brumate 趋势业务 SQL 回归：`Brumate 2026年6月份订单销售额趋势`，禁止月汇总，要求 `GROUP BY report_date`，并在数据库执行时校验返回 30 行。
- 验证通过：相关测试 37 passed；业务 SQL 回归实际执行 13 passed；全量测试 112 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认趋势问题识别为时间序列图。

---

# 月度聚合 GROUP BY 别名报错修复计划

## Spec

目标：修复 Brumate 月度订单销售额 SQL 使用 `to_char(report_date, 'YYYY-MM') AS month` 但 `GROUP BY month` 导致数据库报 `report_date must appear in the GROUP BY clause` 的问题；将规则前置到 SQL Checker，避免同类 SQL 再进入数据库执行。

边界：
- 不改数据库数据。
- 保持月度展示列可命名为 `month`。
- 只禁止月度日期表达式使用 `GROUP BY month` 这类别名分组；正确写法是 `GROUP BY 1` 或 `GROUP BY to_char(report_date, 'YYYY-MM')`。

## Checklist

- [x] 记录 lessons，沉淀月度别名分组规则
- [x] 更新 Prompt/Catalog 文案，明确禁止 `GROUP BY month`
- [x] 增加 SQL Checker 规则和单测
- [x] 增加 Brumate 月度订单销售额 SQL 回归
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 已从 `storage/query_logs.sqlite3` 定位失败 SQL：`to_char(report_date, 'YYYY-MM') AS month` 搭配 `GROUP BY month`，数据库报 `report_date must appear in the GROUP BY clause`。
- 根因不是 Brumate 权限，也不是 `ordered_revenue` 字段；是月度表达式使用了输出别名分组。当前规则要求改成 `GROUP BY 1` 或 `GROUP BY to_char(report_date, 'YYYY-MM')`。
- 已更新 `lessons.md`、`system_prompt.md`、`docs/metric_catalog.md`、`tables/intermediate_amazon.md`，明确月度聚合禁止 `GROUP BY month`。
- 已新增 SQL Checker 规则：检测到 `to_char(report_date, 'YYYY-MM') AS month` + `GROUP BY month` 时，执行前直接返回业务规则错误，要求改为 `GROUP BY 1` 或原表达式。
- 已新增单测覆盖坏 SQL 被拦截、好 SQL 通过。
- 已新增 Brumate 真实问法回归：`Brumate 2026年6月份订单销售额数据`，期望 SQL 使用 `GROUP BY 1`，并实际执行通过。
- 验证通过：相关测试 45 passed；业务 SQL 回归实际执行 12 passed；全量测试 109 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认 `GROUP BY month` 被拦截、`GROUP BY 1` 通过。

---

# 销售额默认口径与月份聚合修正计划

## Spec

目标：落实用户纠正：一般销售额默认用订单中间表 `ordered_revenue`；月份问题默认聚合为月度总数据，例如 2026-06 一行，而不是生成 30 条日明细后被飞书卡片只展示前 10 行。

边界：
- 不改变数据库数据，只更新规则、Catalog、回归用例和测试。
- 保留显式 Business Report / Sessions / 转化率 / 广告归因销售额的专用口径。
- 保留显式“每天/按日/每日趋势”问题的日粒度查询。

## Checklist

- [x] 更新 lessons，沉淀用户纠正规则
- [x] 调整澄清层，不再追问通用销售额口径
- [x] 更新 system prompt、指标 Catalog 和中间表总则的月度聚合规则
- [x] 增加/更新业务 SQL 回归用例和测试
- [x] 运行测试、SQL 回归和服务健康检查

## Review

- 已更新 `lessons.md`：通用销售额默认 `SUM(ordered_revenue)`；月份问题默认月度汇总一行，只有明确“每天/按日”才输出日明细。
- 已调整澄清层：`看一下 2026年7月 销售额` 不再追问口径，会进入 SQL 生成；缺时间的 `看一下销售额` 仍会追问时间范围。
- 已更新 `system_prompt.md`、`docs/metric_catalog.md`、`tables/intermediate_amazon.md`：明确销售额默认订单中间表，月度问题用 `to_char(report_date, 'YYYY-MM') AS month` / `GROUP BY 1`。
- 已新增业务 SQL 回归 `intermediate_orders_monthly_sales_june_2026`，覆盖 2026-06 Belli Welli 月度销售额/销量/订单数，禁止误用 `salesbyasin_orderedproductsales_amount`、`GROUP BY report_date` 和 `LIMIT 10`。
- 验证通过：相关测试 31 passed；业务 SQL 回归实际执行 11 passed；全量测试 107 passed，2 个上游 warning。
- Docker 已重建启动，`data-agent` healthy；`/health` 返回 ok；容器内 smoke 确认销售额不澄清且 prompt 包含 `SUM(ordered_revenue)` 和月聚合规则。

---

# brumate 中间订单 view 权限报错排查计划

## Spec

目标：修复用户查询 `intermediate_amazon_3p_orders_brumate_view` 报 `permission denied for view` 的问题；核查当前账号对该 view 及同类中间表的真实可执行权限，并更新 Catalog，避免 LLM 再选择不可执行对象。

边界：
- 不输出数据库账号、密码、连接串、token 等敏感信息。
- 只做只读权限和 `SELECT 1 ... LIMIT 1` 探针，不修改数据库数据。
- 如果 PostgreSQL catalog 权限与实际 SELECT 不一致，以实际 SELECT 结果为准。

## Checklist

- [x] 核查 `intermediate_amazon_3p_orders_brumate_view` 权限和实际 SELECT
- [x] 扫描同类 `intermediate_amazon_3p_orders_%_view` 实际可执行性
- [x] 确认无需排除 Catalog 表，根因是容器仍使用旧账号
- [x] 补充 Docker `.env` 更新操作说明
- [x] 运行验证并重启/重建服务

## Review

- 宿主机正式连接路径已使用 `pgethan`，`intermediate_amazon_3p_orders_brumate_view` 的 `has_table_privilege(..., 'SELECT')=true`，且 `SELECT 1` 成功。
- Docker 容器内复现用户报错：容器仍使用旧用户 `pginnerbrightness`，该用户对 brumate view 无 SELECT，实际 `SELECT 1` 报 `permission denied for view intermediate_amazon_3p_orders_brumate_view`。
- 根因：之前只执行了 `docker compose restart data-agent`；Docker restart 不会重新读取 `env_file` 中更新后的 `.env` 变量。
- 已执行 `docker compose up -d --force-recreate data-agent`，容器内当前用户变为 `pgethan`，brumate view `SELECT 1` 成功。
- 容器内 brumate 业务查询已实跑成功：2026-05 每日 `SUM(ordered_revenue)` / `SUM(ordered_units)` 返回 5 行样例，无数据库错误。
- 同类 `intermediate_amazon_3p_orders_%` 限时探针结果：35 个 view 中 23 个 3 秒内返回，12 个为 3 秒超时；没有发现权限失败。超时是视图计算成本问题，不是权限问题。
- 已更新 `README.md`：`.env` 改动后必须使用 `docker compose up -d --force-recreate data-agent`，不能只 restart。
- 验证通过：`tests/test_config.py tests/test_catalog.py` 为 9 passed；`/health` 返回 ok。

---

# 品牌店铺 Scope Map 落地计划

## Spec

目标：将 `intermediate_amazon_` 表名后缀解析出的品牌/店铺/市场 scope token 固化成机器可读映射，并接入 Prompt 路由评分，让自然语言品牌名、店铺名、市场后缀能稳定命中对应中间表。

边界：
- 不查询敏感配置。
- 基于现有 `tables_metadata.json` / `intermediate_amazon_profile.json` 生成映射，不重新重扫大视图。
- 映射文件要同时服务机器路由和人工排查。

## Checklist

- [x] 生成 scope alias JSON 和 Markdown
- [x] Prompt 路由接入 scope alias 评分
- [x] 增加品牌/店铺路由测试
- [x] 运行全量验证

## Review

- 新增 `scripts/build_scope_aliases.py`，从 `tables_metadata.json` 生成 scope alias 映射，不依赖数据库重扫。
- 新增 `src/data_agent/data_catalog/scope_aliases.json`，当前覆盖 94 个 scope token，记录 aliases、market、domain -> table 映射、identity values。
- 新增 `docs/intermediate_amazon_scope_map.md`，用于人工查看品牌/店铺/市场到中间表族的覆盖关系。
- 已接入 `prompt_builder.py`：表评分优先使用 `scope_token` + alias 匹配；自然语言品牌名如 `Belli Welli`、`Inner brightness-New`、`VP US`、`Beekeeper CA` 能稳定路由到对应中间表。
- 已增强表族评分：明确 campaign / advertised product / targeting / placement 时优先对应 AMS 表族，避免同一 scope 下多个 AMS 表并列误入。
- 新增测试覆盖 scope alias 路由：`VP US 7月 DSP ROAS`、`Beekeeper CA 7月退货原因`、`Inner brightness-New 7月 AMS campaign 花费`。
- 验证通过：`tests/test_catalog.py` 为 7 passed；`.venv/bin/python -m pytest -q` 为 105 passed，2 个上游弃用 warning；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；Docker `data-agent` 已重启，`/health` 返回 ok。

---

# 中间表深度画像、Catalog 丰富化与旧文档清理计划

## Spec

目标：深入探索 `intermediate_amazon_` 中间表的数据内容，将 Catalog 从结构级升级为数据画像级；清理旧 Innerbrightness 专用表文档，避免后续误用旧表；补充指标词典、品牌/店铺/市场映射、最新业务日期和数据范围。

边界：
- 不输出数据库账号、密码、连接串、token 等敏感信息。
- 只读查询中间表的计数、日期范围、身份字段取值样例和少量统计，不修改数据库数据。
- 旧 Innerbrightness 专用表文档从主 Catalog 中清除；如保留，仅作为归档且不会进入 Prompt。
- Catalog 丰富化优先写入机器可读 JSON 和稳定 Markdown 汇总，避免人工维护 462 张表的重复说明。

## Checklist

- [x] 新增中间表数据画像脚本
- [x] 生成品牌/店铺/市场映射和表族画像文档
- [x] 回填 `latest_business_date`、日期范围、非空 identity 字段到 Catalog
- [x] 更新指标词典和 `docs/metric_catalog.md` 为中间表口径
- [x] 清理旧 Innerbrightness 表文档入口
- [x] 运行数据库实跑和全量测试验证

## Review

- 新增 `scripts/profile_intermediate_data.py`，生成中间表数据画像并回填 `tables_metadata.json`。全量关系来自系统目录和表名解析；数据探针限定在代表性中间表，避免大型视图全量扫描拖垮数据库。
- 新增 `docs/intermediate_amazon_profile.json` 和 `docs/intermediate_amazon_profile.md`：覆盖 462 张中间表、13 个 domain、scope token/品牌店铺映射、代表表日期范围和 identity 字段样例。
- 表族画像显示：DSP 160 张、AMS advertised product 46 张、AMS campaigns 35 张、orders 35 张、Business Report 34 张、AMS search terms 34 张、AMS placement 32 张、AMS targeting 29 张等。
- Top scope token 包括 `belliwelli`、`brumate`、`blueland`、`lider_us`、`perfectbar`、`beekeeper_us`、`supergut`、`innerbrightness` 等，确认当前是多品牌/多店铺数据范围。
- `tables_metadata.json` 已回填 `scope_token`、`row_count`、`min_business_date`、`latest_business_date`、`identity_fields`；因部分大型视图日期聚合超时，未探针表保留结构级 metadata。
- 已重写 `docs/metric_catalog.md` 为中间表口径：订单用 `ordered_revenue/ordered_units/order_items`，AMS 用 `ams_spend/ams_sales/ams_orders/ams_impression/ams_click`，DSP 用 `dsp_*` 字段。
- 已更新 `metric_synonyms.json`，自然语言字段选择会优先命中 `ams_spend`、`ams_sales`、`dsp_cost`、`dsp_total_sales`、`ordered_revenue`、`trafficbyasin_sessions` 等中间表字段。
- 已删除旧表 Markdown：`innerbrightness_3p.md`、`innerbrightness_ads_sp.md`、`innerbrightness_ads_sb.md`、`innerbrightness_inventory_ops.md`；`tables/` 目录仅保留 `intermediate_amazon.md`。
- 已删除旧表索引建议脚本 `scripts/add_recommended_indexes.sql`，避免误执行旧原始表索引建议。
- 已清理 `prompt_builder.py` 和 `sql_checker.py` 中旧原始表专项路由/业务规则，保留中间表主路径。
- 验证通过：`.venv/bin/python -m pytest -q` 为 104 passed，2 个上游弃用 warning；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；Docker `data-agent` 已重启，`/health` 返回 ok。

---

# 中间表数据源切换与品牌店铺关系梳理计划

## Spec

目标：将数据源策略从 Innerbrightness 专用业务表切换为 `intermediate_amazon_` 开头的中间表体系；从中间表的命名、字段结构和轻量样例出发，梳理品牌/店铺/市场/报表类型关系，并更新项目文档与 Data Catalog 相关说明。

边界：
- 不输出数据库账号、密码、连接串、token 等敏感信息。
- 只读查询 PostgreSQL 系统目录和少量样例值，不修改数据库数据。
- 以 `intermediate_amazon_` 中间表为后续分析主数据源；旧 Innerbrightness 专用表仅作为历史参考。
- 优先形成可维护的关系文档和 Catalog 路由规则，不一次性手写 462 张表的完整字段释义。

## Checklist

- [x] 盘点 `intermediate_amazon_` 表族命名模式、对象类型和字段结构
- [x] 识别品牌/店铺/市场/报表类型关系
- [x] 找出当前文档和 Data Catalog 中 Innerbrightness 专用假设
- [x] 更新文档，明确所有数据使用中间表
- [x] 更新 Catalog/Prompt 路由规则，优先选择中间表
- [x] 运行验证并补充 Review

## Review

- 当前账号可 SELECT 的 `intermediate_amazon_%` 对象共 462 个，字段共 15462 个，覆盖多品牌/多店铺/多站点。
- 表族分布包括：3P orders、3P Business Report sales_and_traffic、AMS campaigns/search_term/targeting/advertised_product/placement、DSP audience/order/product/funnel、FBA returns、FBA inventory days 等。
- 品牌/店铺/市场关系主要来自表名后缀：`intermediate_amazon_<report_family>_<brand_or_store>[_<market>]_view`；表内再通过 `brand`、`customer`、`customer_name`、`country`、`country_code`、`profile_name` 等字段补充过滤。
- 新增 `scripts/build_intermediate_catalog.py`，可从 PostgreSQL `pg_catalog` 重新生成中间表 `tables_metadata.json`、`tables_columns.json`、`allowed_columns.json`。
- 已生成新的结构化 Catalog：462 张中间表均 `select_permission=true`，统一挂载到 `intermediate_amazon.md`。
- 新增 `src/data_agent/data_catalog/tables/intermediate_amazon.md`，明确中间表为主数据源，旧 Innerbrightness 专用表仅历史参考。
- 已重写 `system_prompt.md`、`relationships.md`、`relationships_examples.md`，移除“只能 Innerbrightness 19 表”的旧假设，改为多品牌/多店铺中间表路由、同族 UNION ALL、多粒度先聚合再 JOIN。
- 已更新 `prompt_builder.py`：支持 metadata 中的 `doc` 字段，按中间表品牌/店铺后缀评分，并在大量表共享文档时只注入与问题相关的 top 表，避免 prompt 膨胀。
- 已将泛问题 fallback 固定到中间表结构化 Catalog，避免未命中路由时加载旧 Innerbrightness Markdown 文档。
- 已更新 `sql_checker.py`：`intermediate_amazon_` 事实表必须带日期过滤；Business Report AVG 转化率规则覆盖中间表。
- 已迁移业务回归集、column selector、query examples 和 Catalog 测试到中间表字段口径；执行验证时发现 `dsp_product` 表没有 `dsp_cost`，已将 DSP ROAS 用例切到 `intermediate_amazon_dsp_order_funnel_belliwelli_view`。
- 验证通过：`.venv/bin/python -m pytest -q` 为 104 passed，2 个上游弃用 warning；`scripts/validate_business_sql_cases.py` 为 10 passed；`scripts/validate_business_sql_cases.py --execute` 为 10 passed；Docker `data-agent` 已重启，`/health` 返回 ok。

---

# intermediate_amazon_ 中间表权限检查计划

## Spec

目标：使用当前 `.env` 中已更新的 PostgreSQL 账号，检查该账号对所有 `intermediate_amazon_` 开头中间表/视图的可见性与 SELECT 权限，并汇总是否存在缺失授权。

边界：
- 不输出数据库账号、密码、连接串、token 等敏感信息。
- 只读查询 PostgreSQL 系统目录和轻量 `SELECT 1` 验证，不修改任何数据库数据。
- 区分对象可见性、`has_table_privilege(..., 'SELECT')` 结果，以及实际轻量 SELECT 是否成功。

## Checklist

- [x] 查询 `intermediate_amazon_%` 对象列表
- [x] 检查每个对象的 SELECT 权限
- [x] 对有权限对象做轻量 SELECT 验证
- [x] 修正 `.env` 与 `postgresql.env` 的配置优先级
- [x] 汇总缺失权限与 Review

## Review

- `.env` 中的新 PostgreSQL 用户为 `pgethan`，但修复前 `get_settings()` 会被旧 `postgresql.env` 覆盖，实际连成旧用户 `pginnerbrightness`。
- 已修复 `src/data_agent/config.py`：只有当系统环境和 `.env` 都没有声明对应 `PG_*` key 时，才使用 `postgresql.env` legacy 回退。
- 使用新账号 `pgethan` 直接检查：`intermediate_amazon_%` 匹配对象 462 个，其中 SELECT 授权 462 个、缺失 0 个。
- 对象类型分布：1 个 materialized view、1 个 table、460 个 view，均有 SELECT 权限。
- 抽样 10 个对象执行 `SELECT 1 FROM ... LIMIT 1`，全部成功。
- 修复后通过正式 `get_connection()` 再次验证：当前用户 `pgethan`，匹配对象 462 个，SELECT 授权 462 个，缺失 0 个。
- 验证通过：`tests/test_config.py` 为 2 passed；全量 `.venv/bin/python -m pytest -q` 为 108 passed，2 个上游弃用 warning。

---

# ROUND 比率类型错误排查与修复计划

## Spec

目标：定位最近一次查询报错原因，并修复 LLM 生成 `ROUND(double precision, integer)` 风险 SQL 的问题。

边界：
- 保留 ACoS/ROAS 等比率防除零规则。
- 增加执行前校验，避免同类 SQL 进入数据库后才报错。
- 更新指标口径和系统 prompt，明确 PostgreSQL 中 `ROUND(expr, n)` 的比率表达式必须转为 numeric。
- 用最近一次失败 SQL 做回归测试。

## Checklist

- [x] 提取最近失败查询日志和 SQL
- [x] 增加 SQL Checker 对 ROUND 比率类型风险的校验
- [x] 更新指标口径和 prompt 中的 ROUND 写法
- [x] 增加回归测试并运行验证
- [x] 重建容器并健康检查

## Review

- 最近一次失败查询是：`2026年6月，广告花费最多的10个asin，以及他们的Business Report销售额和acos`。
- 报错原因不是飞书或权限问题，而是 PostgreSQL 类型问题：LLM 生成了 `ROUND(t.ad_spend::numeric / NULLIF(t.ad_sales, 0), 4)`，其中 `t.ad_sales` 来自 `SUM(sales14d)`，表达式最终被推断为 `double precision`，PostgreSQL 不支持 `round(double precision, integer)`。
- 正确写法是 `ROUND((t.ad_spend / NULLIF(t.ad_sales, 0))::numeric, 4)`，或确保分子分母都显式为 numeric。
- 已新增 SQL Checker 规则，提前拦截金额/销售额/花费类分母未 numeric 的 `ROUND(除法表达式, 位数)` 风险，避免进入数据库后才报错。
- 已更新 `docs/metric_catalog.md`、`system_prompt.md`、SP/SB Catalog 示例、relationships 示例和 eval SQL，统一使用 PostgreSQL 兼容写法。
- 已用修正后的最近 SQL 实际执行成功：返回 10 行，字段为 `asin, ad_spend, ad_sales, acos, br_sales`。
- 验证通过：`tests/test_sql_checker.py` 15 passed；全量测试 59 passed；业务 SQL 回归 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内 smoke test 确认旧坏写法会被 checker 拦截，新写法通过。

---

# 图表规格与百分比展示优化计划

## Spec

目标：固定每类图表的视觉格式，统一百分比指标展示，并沉淀图表规范文档，减少模型或代码临场发挥导致的展示不稳定。

边界：
- 本轮先优化已有表格、柱状图、折线图能力，不引入新的前端图表服务。
- 百分比指标通过列名语义识别，包括转化率、CVR、ACoS、ROAS、CTR 等。
- 数值在 Feishu 卡片表格、Markdown 表格、图表坐标轴和图表标注中统一格式化。
- 固定图表主题、尺寸、颜色、网格、标签策略，并文档化。

## Checklist

- [x] 新增图表规格文档
- [x] 增加指标格式识别和百分比格式化
- [x] 优化柱状图/折线图固定视觉主题
- [x] 更新卡片表格百分比展示
- [x] 增加测试并运行验证

## Review

- 新增 `docs/chart_catalog.md`，固定图表类型、指标格式、柱状图、折线图和表格展示规范。
- 新增 `src/data_agent/visualization/formatting.py`，统一识别百分比、金额、数量和普通数值指标。
- 百分比字段如 `conversion_rate`、`acos`、`ctr`、`tacos` 现在展示为 `12.34%`，并在 Markdown 表格、飞书卡片表格、图表坐标轴和图表标签中复用同一规则。
- 柱状图从默认竖向柱图改为固定横向柱图，使用统一颜色、网格、标题、标签和边框样式，更适合 ASIN/SKU/campaign 等长分类标签。
- 折线图统一颜色、线宽、点样式、网格和 y 轴格式。
- 验证通过：可视化/卡片测试 8 passed；全量测试 56 passed；业务 SQL 回归 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内 smoke test 确认 `conversion_rate` 表格展示为百分比，图表输出有效 PNG。

---

# 指标口径 Catalog 文档落地计划

## Spec

目标：新增一份人工可审阅的指标口径文档，沉淀核心指标定义、默认数据源、SQL 表达式、适用/不适用场景和注意事项，并让 SQL 生成 prompt 明确优先遵循该口径。

边界：
- 本轮先做 Markdown 文档和 prompt 引用，不引入结构化 YAML/JSON 指标引擎。
- 重点覆盖当前高频且容易混淆的口径：销量、销售额、Sessions、转化率、广告指标、库存/履约指标。
- 文档以人工复核为主，表达式保持可读，不强制成为代码生成源。
- 不改 SQL 执行链路。

## Checklist

- [x] 新增 `docs/metric_catalog.md`
- [x] 在 system prompt 增加优先遵循指标口径 Catalog 的规则
- [x] 运行测试和编译检查
- [x] 更新 Review

## Review

- 新增 `docs/metric_catalog.md`，覆盖销售/订单、Business Report 流量转化、跨日下滑、广告、库存履约等核心指标口径。
- 文档明确了“销量 + Sessions/转化率必须使用 Business Report”“下滑量使用 previous - current 并过滤 decline > 0”“比率必须防除零”等规则。
- 更新 `src/data_agent/data_catalog/system_prompt.md`，要求 SQL 生成优先遵循指标口径 Catalog，避免订单口径、Business Report 口径和广告归因口径混用。
- 验证通过：全量测试 52 passed；`compileall` 通过。

---

# Business Report CASE/COALESCE 防除零误判二次修复计划

## Spec

目标：修复 SQL Checker 对 `CASE WHEN COALESCE(alias.sessions, 0) > 0 THEN ... / alias.sessions` 这类安全防除零写法的误判。

边界：
- 保留 Business Report 转化率必须防除零的规则。
- 继续拒绝裸除法。
- 新增用户刚刚提供的完整 SQL 作为回归测试。
- 修复后重建 Docker，并在容器内验证同一 SQL 返回合法。

## Checklist

- [x] 扩展 SQL Checker 对 qualified column 和 COALESCE guard 的识别
- [x] 增加用户本次 SQL 回归测试
- [x] 运行单测、全量测试、业务回归和编译检查
- [x] 重建容器并容器内验证

## Review

- 根因是第一次修复只识别 `CASE WHEN sessions_24 > 0 THEN ... / sessions_24`，没有覆盖 LLM 实际生成的 `CASE WHEN COALESCE(d24.sessions_24, 0) > 0 THEN ... / d24.sessions_24`。
- 已扩展 SQL Checker：安全 CASE 除法识别前会去掉表别名前缀，并支持 guard 侧使用 `COALESCE(denominator, 0) > 0`。
- 已把用户本次贴出的完整 SQL 加入回归测试，避免只用简化 SQL 误判修复完成。
- 验证通过：`tests/test_sql_checker.py` 为 12 passed；全量测试为 52 passed；业务 SQL 回归脚本为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内对用户本次 SQL 调用 `validate_business_sql()` 返回 `(True, '')`。

---

# Business Report 转化率 Checker 误判与 SQL 截断修复计划

## Spec

目标：修复“2026-06-24 对比 2026-06-23 销量下滑最多 ASIN”查询中，SQL Checker 对安全 CASE 防除零写法的误判，并降低 LLM SQL 代码块被截断导致提取失败的概率。

边界：
- 保留 Business Report 转化率必须防除零的业务规则。
- 允许 `NULLIF(...)` 和 `CASE WHEN denominator > 0 THEN numerator / denominator ELSE ... END` 两类安全写法。
- 不放宽到允许裸除法。
- LLM 截断先通过提高 `max_tokens` 和 prompt 明确要求完整 SQL 代码块来解决，不引入二次续写复杂流程。
- 增加回归测试覆盖本次实际 SQL。

## Checklist

- [x] 修改 SQL Checker 防除零识别逻辑
- [x] 增加本次实际 SQL 的回归测试
- [x] 调整 LLM max_tokens / prompt 完整输出要求
- [x] 运行测试、SQL 回归、容器重建和健康检查

## Review

- 修复了 SQL Checker 误判：Business Report 转化率除法现在接受 `NULLIF(...)`，也接受 `CASE WHEN denominator > 0 THEN numerator / denominator ELSE ... END` 这种同分母防除零写法。
- 保留了裸除法拦截，错误信息调整为“必须使用 NULLIF 或 CASE WHEN 防止除零”。
- 新增本次实际失败 SQL 的回归测试，并新增裸除法反向测试，避免规则被放得过宽。
- 将 LLM `max_tokens` 从硬编码 2000 改为配置项 `LLM_MAX_TOKENS`，默认 4000，并更新 `.env.example`。
- 更新系统 prompt，要求 SQL 代码块必须完整闭合，长 SQL 优先保留完整可执行 SQL，降低首次回复被截断后无法提取 SQL 的概率。
- 验证通过：`tests/test_sql_checker.py` 为 11 passed；全量测试为 51 passed；业务 SQL 回归脚本为 10 passed；`compileall` 通过。
- Docker 已重建，服务健康检查返回 `{"status":"ok","service":"shu-tan"}`；容器内对本次 SQL 调用 `validate_business_sql()` 返回 `(True, '')`。
- 工作区不是 git 仓库，无法使用 `git diff/status` 做最终差异检查，已改用测试、容器和文件级验证收口。

---

# 2026-06-24 ASIN 下滑查询报错根因排查计划

## Spec

目标：定位用户问题“查询2026-06-24对比2026-06-23销量下滑最多的5个asin，以及6月24日的当日销量和转化率”触发 SQL Checker 报错的真实原因，判断是 LLM SQL 口径问题、checker 误判，还是 Catalog/澄清规则不足。

边界：
- 本轮先找根因，除非根因明确且修复很小，否则不急着改规则。
- 不泄露数据库凭证。
- 优先从 SQLite query log 和容器日志读取失败 SQL。
- 如果日志没有记录，再用本地复现问题。

## Checklist

- [x] 查 SQLite query log 中该问题的失败记录
- [x] 提取 LLM 原始回复和 SQL
- [x] 对照 SQL Checker 规则分析触发条件
- [x] 判断正确 SQL 应如何写
- [x] 给出根因和建议修复点

## Review

- SQLite 中有两条相关记录：原始问题记录状态为 `llm_clarification`，因为 LLM 回复在 SQL 代码块中途被截断，`extract_sql()` 没有提取到完整 SQL。
- 用户回复“确认”后，第二条记录状态为 `error`，SQL 已完整生成。
- 触发报错的 SQL 使用 `CASE WHEN sessions_24 > 0 THEN units_24::numeric / sessions_24 ELSE 0 END` 防除零。
- 当前 SQL Checker 规则只接受 `NULLIF`，看到 Business Report 表中同时出现 sessions、units 和除法但没有 `NULLIF`，就报“必须使用 NULLIF 防止除零”。
- 根因是 SQL Checker 误判：它没有识别 `CASE WHEN denominator > 0 THEN numerator / denominator ELSE 0 END` 这种同样安全的防除零写法。
- 次要问题是 LLM 首次回复被截断，导致用户需要回复“确认”才拿到完整 SQL。

---

# 反馈复盘导出脚本实施计划

## Spec

目标：新增反馈复盘脚本，从 SQLite 查询日志中导出需要人工复盘的反馈记录，生成 Markdown 报告，为后续更新 eval、Catalog、clarifier、SQL checker 提供输入。

边界：
- 只读 SQLite，不修改日志数据。
- 默认导出口径不对、没查到我想要的、unknown 等非准确反馈。
- 支持输出全部反馈或指定天数范围。
- 不输出密钥和连接信息。
- 报告落在 `docs/feedback_review.md`，可重复生成。

## Checklist

- [x] 设计反馈复盘 SQL
- [x] 新增 `scripts/review_feedback.py`
- [x] 支持 Markdown 输出和命令行参数
- [x] 增加测试
- [x] 运行测试和脚本 smoke test

## Review

- 新增 `scripts/review_feedback.py`，只读 SQLite，将反馈与原查询关联导出为 Markdown。
- 默认导出口径不对、没查到我想要的、unknown 等需复盘反馈；可用 `--include-accurate` 包含准确反馈。
- 支持 `--db`、`--output`、`--days`、`--include-accurate` 参数。
- 默认报告输出到 `docs/feedback_review.md`。
- 新增 `tests/test_review_feedback.py`，覆盖默认只导出需复盘反馈、可包含准确反馈。
- 当前运行生成 `docs/feedback_review.md`，真实反馈记录数为 0，因此报告为空队列。
- 验证通过：`.venv/bin/python -m pytest -q` 为 49 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy。

---

# SQLite 查询日志与反馈闭环实施计划

## Spec

目标：新增 SQLite 持久化日志，记录每次用户查询、澄清、LLM 回复、SQL、执行结果和用户反馈；在结果卡片增加反馈按钮，形成后续复盘和 eval/Catalog 迭代的数据来源。

边界：
- 日志先存本地 SQLite，不引入外部服务。
- SQLite 文件默认放 `storage/query_logs.sqlite3`，不进入 Docker 镜像和 git。
- 不记录密钥、数据库密码、飞书 token。
- 记录用户问题、SQL、错误、反馈等必要排查信息。
- 反馈按钮包括：准确、口径不对、没查到我想要的。
- 卡片回调继续兼容 `card.action.trigger`。

## Checklist

- [x] 新增 SQLite 日志模块和 schema
- [x] 查询/澄清/错误/成功时写入日志
- [x] 结果卡片增加反馈按钮并携带 query_id
- [x] 卡片回调处理 feedback 并更新 SQLite
- [x] 更新 Docker/.gitignore 配置
- [x] 增加测试
- [x] 运行测试、SQL 回归、容器重建和健康检查

## Review

- 新增 `src/data_agent/session/query_log.py`，使用标准库 SQLite，包含 `query_events` 和 `feedback_events` 两张表。
- 默认 SQLite 路径为 `storage/query_logs.sqlite3`，并新增 `QUERY_LOG_DB_PATH` 到 `.env.example`。
- `.gitignore` 和 `.dockerignore` 已忽略 `storage/`；`docker-compose.yml` 已挂载 `./storage:/app/storage`，容器重建不会丢日志。
- 飞书消息进入处理后会创建 query event；澄清、LLM 澄清、错误、成功都会更新状态、SQL、行数、列名、耗时等信息。
- 结果卡片新增反馈按钮：准确、口径不对、没查到我想要的；按钮携带 `query_id`。
- `card.action.trigger` 已支持 `feedback`，点击后写入 `feedback_events` 并回复“反馈已记录”卡片。
- 新增 `tests/test_query_log.py`，并更新卡片/webhook 测试覆盖 query log 和 feedback。
- 验证通过：`.venv/bin/python -m pytest -q` 为 47 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内写入 SQLite 并从宿主机读到记录，随后已删除 smoke 测试库，真实查询会自动创建。

---

# 飞书卡片按钮无响应排查与修复计划

## Spec

目标：修复结果卡片中的“看趋势图 / 下钻明细 / 查看 SQL”按钮点击无响应问题，确保飞书卡片回调能正确识别点击事件并在当前话题内回复。

边界：
- 不改变查询生成和 SQL 执行逻辑。
- 优先通过日志和本地模拟确认回调 payload 结构。
- 若飞书回调字段名兼容不足，补充多格式解析。
- 若缺少事件回调日志，增加安全日志，不打印密钥和敏感消息内容。
- 增加测试覆盖卡片按钮 payload。

## Checklist

- [x] 查看容器日志确认按钮回调是否到达
- [x] 检查 `/feishu/card` 回调 payload 解析
- [x] 本地模拟飞书按钮回调
- [x] 修复字段兼容或回复逻辑
- [x] 增加测试
- [x] 重建容器并验证健康检查

## Review

- 日志确认按钮点击已到达服务，但飞书把点击事件作为加密 `card.action.trigger` 推送到 `/feishu/webhook`，原代码只处理 `im.message.receive_v1`，所以被忽略。
- 已让 `/feishu/webhook` 识别并处理 `card.action.trigger`，复用卡片动作处理逻辑。
- `/feishu/card` 仍保留，并复用同一套 `_handle_card_action()`。
- 新增 `_extract_action_value()`，兼容 `action.value` 为 dict 或 JSON string 的 payload。
- 新增 `_extract_card_message_id()`，兼容 `open_message_id`、`message_id`、`event.context.open_message_id` 等多种位置。
- 增加测试覆盖 `show_sql` 和 string value 的卡片动作。
- 验证通过：`.venv/bin/python -m pytest -q` 为 44 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内验证可从 `card.action.trigger` payload 解析出 `show_sql` 和 `om_card`。

---

# 结构化澄清机制实施计划

## Spec

目标：在 LLM 生成 SQL 前新增轻量澄清层，对时间范围、销售额口径、广告类型、库存口径、商品标识等关键歧义进行拦截和追问，减少模型硬猜导致的业务口径错误。

边界：
- 首轮使用确定性规则，不引入额外 LLM intent 分类。
- 只在明显缺少关键信息时追问；能从上下文或明确关键词判断时继续生成 SQL。
- 澄清回复不执行 SQL、不调用数据库。
- 覆盖群聊话题和单聊的现有流程，不破坏 @ 机器人和 thread 回复逻辑。
- 增加单元测试和 webhook 流程测试。

## Checklist

- [x] 阅读 webhook/LLM 调用链路
- [x] 新增 clarifier 模块
- [x] 在消息处理流程中接入澄清层
- [x] 增加澄清规则测试
- [x] 增加 webhook 不调用 LLM/DB 的测试
- [x] 运行测试、SQL 回归、容器重建和健康检查

## Review

- 新增 `src/data_agent/agent/clarifier.py`，在 LLM 生成 SQL 前做确定性澄清判断。
- 当前覆盖：缺时间范围、销售额口径歧义、广告类型歧义、库存口径歧义、缺 ASIN/SKU 商品标识。
- `_handle_user_query()` 已接入澄清层；需要澄清时写入会话历史并返回澄清卡片，不调用 DeepSeek，也不执行数据库查询。
- 新增 `tests/test_clarifier.py`，覆盖典型歧义和上下文补全。
- 更新 `tests/test_feishu_webhook.py`，验证歧义问题不会调用 LLM，清晰问题仍进入 LLM + SQL 执行流程。
- 验证通过：`.venv/bin/python -m pytest -q` 为 42 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内验证“看一下 2026年7月 销售额”返回“需要确认信息”澄清卡片。

---

# SQL Checker 业务规则校验实施计划

## Spec

目标：在 SQL 执行前新增业务规则校验层，拦截“语法安全但业务口径错误”的 SQL，提升 Text-to-SQL 结果可靠性。

边界：
- 保留现有 `validate_sql()` 的只读安全校验。
- 新增 checker 先做确定性规则，不引入额外 LLM 审查。
- 首轮覆盖高风险规则：Catalog 外表、缺日期过滤、PII 字段、Business Report 转化率 AVG、SP/SB 字段混用、purchased product 表误算花费/ACoS、订单表缺 shipped 过滤。
- 执行前调用业务 checker；失败时不查数据库，直接返回错误提示。
- 更新 SQL 回归和单元测试。

## Checklist

- [x] 阅读 SQL 执行器和回归脚本
- [x] 实现业务规则 checker
- [x] 接入 `execute_query`
- [x] 增加单元测试覆盖高风险错误
- [x] 运行测试、SQL 回归、容器重建和健康检查

## Review

- 新增 `src/data_agent/agent/sql_checker.py`，在只读安全校验之外增加业务规则校验。
- `execute_query()` 已在连接数据库前调用业务 checker；失败时直接返回“业务规则校验失败”，不会打开数据库连接。
- `scripts/validate_business_sql_cases.py` 已接入业务 checker，回归用例会同时校验安全规则和业务规则。
- 首轮覆盖规则：Catalog 外/无权限表、事实表缺日期过滤、PII 字段、订单表缺 Shipped 过滤、Business Report 转化率误用 AVG、SP/SB 销售/购买字段混用、purchased product 表误算花费/ACoS、订单与广告明细直接 JOIN。
- 新增 `tests/test_sql_checker.py` 和执行器负例测试，覆盖高风险错误。
- 验证通过：`.venv/bin/python -m pytest -q` 为 31 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内验证 Business Report `AVG(trafficbyasin_unitsessionpercentage)` 被业务 checker 拦截。

---

# Data Catalog 表检索路由实施计划

## Spec

目标：基于 `tables_metadata.json` 实现第一层表检索路由，让每次用户问题只加载相关表的详细 Catalog，而不是全量塞入所有表文档，提升选表准确性并降低 prompt 噪声。

边界：
- 保持现有 LLM 调用接口不变。
- 不引入外部向量库；先用确定性关键词/领域匹配，便于测试和解释。
- system prompt、metadata 摘要和 relationships 继续加载；表级 Markdown 只加载命中的 1-4 个文档。
- 如果无法匹配，保守加载全部表文档，避免功能倒退。
- 更新测试覆盖 Business Report、SP/SB 搜索词、库存、退货、订阅等路由。

## Checklist

- [x] 阅读当前 prompt builder 和 Catalog 文件结构
- [x] 实现 metadata 解析与关键词匹配
- [x] 改造 `build_messages` 只加载相关表文档
- [x] 增加路由单元测试
- [x] 运行测试、SQL 回归、容器重建和健康检查

## Review

- 已在 `prompt_builder.py` 实现 `tables_metadata.json` 解析、确定性表打分和文档组路由。
- `build_messages()` 现在会根据用户问题和最近用户上下文选择相关表文档；无法匹配时保守回退全量 Catalog。
- 当前路由粒度是文档组：3P、库存运营、SP、SB。后续可继续细化到单表片段。
- 已处理 SP/SB 显式问题互斥，避免“SP 搜索词”同时加载 SB 详细文档，反之亦然；`SP+SB TACOS` 会同时加载 3P、SP、SB 文档。
- 新增测试覆盖 Business Report、SP/SB 搜索词、SP+SB TACOS、库存补货、退货、订阅和兜底全量加载。
- 验证通过：`.venv/bin/python -m pytest -q` 为 21 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；`compileall` 通过。
- Docker 已重建且 healthy；容器内验证 Business Report 问题只加载 `innerbrightness_3p.md`，prompt 从约 39.8k 字符降到约 22.0k；TACOS 问题加载 3P、SP、SB，prompt 约 33.9k。

---

# 真实数据库 Data Catalog 落地实施计划

## Spec

目标：基于 `docs/database_inventory.json` 中当前账号真实可 SELECT 的 19 张 Innerbrightness 表，重建机器可读 Data Catalog，使机器人后续能按业务域、关键词、权限、字段和指标规则更精准地生成 SQL。

边界：
- 只基于当前账号可 SELECT 的表落地运行时 Catalog。
- 不把 2131 张可见但无权限的全量表塞进运行时 prompt。
- Catalog 文件应包含用途、适用/不适用场景、权限、数据新鲜度、粒度、日期字段、关键维度、关键指标、默认过滤、正确示例、错误示例或注意事项。
- 新增 `tables_metadata.json` 作为第一层表检索元数据，但本轮先保持 prompt 全量加载，避免一次性引入检索路由风险。
- 更新测试，确保 Catalog 与真实权限状态一致。

## Checklist

- [x] 从 `database_inventory.json` 提取 19 张可 SELECT 表字段和日期状态
- [x] 新增 `tables_metadata.json`
- [x] 重建 3P/广告/库存运营 Catalog 文档
- [x] 更新 system prompt 和 relationships 中过期权限说明
- [x] 更新 Prompt Builder 加载 metadata
- [x] 更新/新增测试
- [x] 运行测试与 SQL 回归

## Review

- 新增 `src/data_agent/data_catalog/tables_metadata.json`，覆盖当前可 SELECT 的 19 张 Innerbrightness 表，记录业务域、关键词、适用/不适用场景、粒度、日期字段、最新业务日期和权限。
- 重写 `innerbrightness_3p.md`，覆盖订单、Business Report、发货、退货、Subscribe & Save，并补充 PII 禁区、转化率聚合规则和真实权限状态。
- 重写 `innerbrightness_inventory_ops.md`，明确库存快照、Inventory Health、Inventory Planning 三类表的选表边界和 text 数值安全转换规则。
- 重写 `innerbrightness_ads_sp.md` 和 `innerbrightness_ads_sb.md`，强化 SP/SB 字段差异、14 天归因、purchased product 无花费字段等硬规则。
- 更新 `system_prompt.md` 当前日期和权限说明；更新 `relationships.md`，移除过期“无 SELECT 权限”说明。
- 更新 `prompt_builder.py`，将 `tables_metadata.json` 加入 system prompt。
- 更新 `evals/innerbrightness_business_questions.json`，退货和订阅用例从权限待开通改为 ready，并数据库实跑通过。
- 更新 `tests/test_catalog.py`，确保 19 张表 metadata 都是 `select_permission=true`，且旧权限文案不会回归。
- Docker 构建已排除 `docs/database_inventory.*`，构建上下文从约 59MB 降到约 5.7KB。
- 验证通过：JSON 校验通过；`compileall` 通过；`.venv/bin/python -m pytest -q` 为 16 passed；`.venv/bin/python scripts/validate_business_sql_cases.py --execute` 为 10 passed；Docker 容器 healthy，容器内 Catalog 已加载 metadata 且无旧权限文案。

---

# 真实数据库全表可见性与权限盘点计划

## Spec

目标：使用当前项目配置的 PostgreSQL 账号，盘点该账号可见的所有业务表、字段结构、SELECT 权限状态，以及可查询表的最新数据日期，为真实数据库 Data Catalog 落地提供基础事实。

边界：
- 不输出数据库密码、连接串、token 等敏感信息。
- 只读访问数据库元数据和轻量聚合，不修改任何数据。
- 最新数据日期优先从日期/时间字段推断；若表无明显日期字段或无 SELECT 权限，则记录为无法判断。
- 结果沉淀到项目文档，后续 Catalog 以该文档为依据。

## Checklist

- [x] 读取当前数据库连接配置和现有扫描脚本能力
- [x] 查询账号可见 schemas/tables/views
- [x] 查询每张表字段、类型、注释、估算行数
- [x] 检查每张表 SELECT 权限
- [x] 对有权限表推断最新数据日期
- [x] 生成数据库盘点文档
- [x] 运行验证并补充 Review

## Review

- 新增 `scripts/inventory_database.py`，使用当前 `.env` / `postgresql.env` 账号只读扫描 PostgreSQL。
- 已生成 `docs/database_inventory.md` 和 `docs/database_inventory.json`。
- 当前账号在非系统 schema 下可见对象 2131 个，字段 174773 个。
- 当前账号有 SELECT 权限的对象 19 个，缺少 SELECT 权限的对象 2112 个，均在 `public` schema。
- 19 个可 SELECT 对象均为 Innerbrightness 相关重点表；之前记录为无权限的发货、FBA Inventory Planning、FBA Returns、Inventory Health、Replenishment Metrics 现在均可 SELECT。
- 报告将“业务最新日期”和“加载/更新时间”分开记录，避免把 `created_at` / `updated_at` 当作业务日期。
- 验证通过：`.venv/bin/python -m pytest -q` 为 15 passed；`.venv/bin/python scripts/validate_business_sql_cases.py` 为 10 passed；`http://127.0.0.1:8010/health` 正常。

---

# PA 精准性方法论对齐与优化路线计划

## Spec

目标：结合 `docs/数据分析PA精准性探因.md` 和当前 `data_agent` 代码，判断后续优化重点，形成一份可执行的迭代路线。

边界：
- 本轮只做阅读、分析和路线建议，不修改业务代码。
- 重点比较当前实现与文档中 Data Catalog、AI_HINT、澄清、自检、评估闭环的差距。
- 输出必须能落到后续工程任务，而不是泛泛而谈。

## Checklist

- [x] 阅读 PA 精准性探因文档
- [x] 检查当前 Data Catalog、Prompt Builder、SQL Executor、LLM Client
- [x] 检查当前 evals 与测试覆盖
- [x] 形成优化方向和迭代优先级

## Review

- 当前项目已经具备 MVP 闭环：飞书事件 -> DeepSeek -> SQL -> PostgreSQL -> 卡片/图表。
- 当前 Data Catalog 已包含 AI_HINT 和业务口径，但仍是“全量拼接进 system prompt”，尚未实现文档里的两层检索、表级精准装载和规则链。
- 当前 SQL 校验主要是安全校验，缺少业务口径自检、表字段合法性检查、权限检查、日期过滤检查和二次修正机制。
- 当前 evals 只有 10 条确定性业务 SQL 用例，缺少真实用户问法、澄清用例、错误案例和线上反馈闭环。
- 后续优化重点应从“能回答”转向“可解释、可验证、可复盘、可扩展地回答”。

---

# 项目架构与功能梳理计划

## Spec

目标：快速但准确地梳理当前项目的模块架构、核心功能、运行入口、数据流、测试与已知边界，给用户一份可用于继续开发或接手的项目说明。

边界：
- 只做阅读、验证和总结，不修改业务代码。
- 不泄露 `.env`、`postgresql.env` 中的敏感连接信息。
- 以代码、测试、Catalog 和现有文档为依据；推断内容明确标注。

## Checklist

- [x] 阅读项目规则、历史 todo/lessons
- [x] 盘点文件结构和依赖
- [x] 阅读 FastAPI 入口、配置、Agent、SQL、会话、飞书、可视化模块
- [x] 阅读 Data Catalog、业务测试集和测试脚本
- [x] 运行验证命令确认当前项目状态
- [x] 输出架构与功能总结

## Review

- 当前项目是一个 FastAPI MVP：飞书消息接入 -> LLM 生成 SQL -> SQL 只读校验 -> PostgreSQL 查询 -> Markdown 表格/图表飞书卡片返回。
- Data Catalog 已收敛为 Innerbrightness 亚马逊业务专用，覆盖订单、Business Report、库存、SP/SB 广告，并标注无 SELECT 权限的运营/退货/补货表。
- 本地 shell 无 `python` 命令，验证需使用 `.venv/bin/python`。
- `.venv/bin/python -m compileall agent feishu session visualization tests config.py main.py` 通过。
- `.venv/bin/python -m pytest -q` 通过：9 passed，1 个 Starlette/FastAPI TestClient 上游弃用 warning。
- `.venv/bin/python scripts/validate_business_sql_cases.py` 通过：10 passed，0 failed。

---

# 飞书群聊 @ 机器人可用性检查计划

## Spec

目标：检查更新后的环境配置是否已满足“在飞书群聊中 @ 对应智能体并收到回复”的基本条件，并通过本地 webhook 事件模拟验证代码链路。

边界：
- 不在回复或文档中泄露 `.env`、`postgresql.env` 的真实密钥、token、密码。
- 只检查配置完整性、服务入口和本地事件处理；不主动向真实飞书群发送测试消息。
- 若发现缺项，明确说明还需要在飞书开放平台或公网回调侧完成什么。

## Checklist

- [x] 检查 `.env` 关键配置是否存在且非空
- [x] 检查飞书 webhook 代码对群聊 @ 消息的处理路径
- [x] 用本地 TestClient 模拟飞书群聊消息事件
- [x] 运行现有测试确认未破坏
- [x] 输出是否可以群聊 @ 使用的结论

## Review

- `.env` 已存在，`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`DEEPSEEK_API_KEY`、PostgreSQL 连接配置均为非空。
- `FEISHU_ENCRYPT_KEY` 和 `FEISHU_VERIFICATION_TOKEN` 当前为空；如果飞书开放平台启用了事件加密或 token 校验，需要补齐并确认代码解密/校验策略。
- 飞书 App ID/Secret 可成功换取 tenant token。
- 本地 TestClient 模拟群聊 @ 消息成功：`/feishu/webhook` 返回 `{"code": 0}`，处理路径会向群聊发“正在查询”卡片并回复结果卡片。
- 飞书 URL challenge 模拟成功返回 challenge。
- DeepSeek 连通性测试成功，数据库 `SELECT 1` 测试成功。
- `.venv/bin/python -m pytest -q` 通过：9 passed，1 个 Starlette/FastAPI TestClient 上游弃用 warning。
- 当前本机 8000 端口未监听，`http://127.0.0.1:8000/health` 不可访问；真实群聊使用前需要启动服务，并保证飞书事件订阅 URL 指向可公网访问的 `/feishu/webhook`。

---

# 飞书群聊 @ 无响应排查与 env 补充计划

## Spec

目标：针对用户在飞书群里 @ 机器人无响应的问题，明确需要配置哪些环境项和飞书开放平台项，并把本项目侧可记录的配置项列入 `.env`。

边界：
- 不展示或覆盖 `.env` 中已有真实密钥。
- 代码当前不从 `.env` 读取事件订阅 URL；该 URL 需要在飞书开放平台后台配置，`.env` 只记录提醒。
- 先不改业务逻辑，只补充可操作配置清单。

## Checklist

- [x] 检查 `.env` 当前飞书相关键
- [x] 在 `.env` 中补充群聊 @ 接收所需配置清单/占位
- [x] 输出飞书后台必须配置的项目

## Review

- 已在 `.env` 飞书段落补充群聊 @ 接收配置清单：`FEISHU_EVENT_SUBSCRIPTION_URL`、`FEISHU_EVENT_NAME=im.message.receive_v1` 以及飞书后台配置提醒。
- 未改动 `.env` 中已有真实 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、DeepSeek、PostgreSQL 配置。
- 当前 `FEISHU_ENCRYPT_KEY`、`FEISHU_VERIFICATION_TOKEN` 仍为空；只有当飞书开放平台启用事件加密或校验 token 时才需要填。
- 当前本机 8000 端口已有 Python 服务监听，`GET /health` 返回 `{"status":"ok","service":"shu-tan"}`。
- `.venv/bin/python -m pytest -q` 通过：9 passed，1 个 Starlette/FastAPI TestClient 上游弃用 warning。
- 群聊 @ 无反应最可能不是 `.env` 的 App ID/Secret 问题，而是飞书开放平台事件订阅 Request URL、事件订阅、机器人入群或权限未配置完成。

---

# Docker 容器化运行计划

## Spec

目标：把当前本地 FastAPI 数探机器人项目放入 Docker 容器运行，暴露 `8000` 端口，便于后续通过 Cloudflare Tunnel 暴露公网入口给飞书事件订阅。

边界：
- 不把 `.env`、`postgresql.env`、本地虚拟环境、缓存、大文件打进镜像。
- 容器通过 `--env-file .env` 或 docker compose 读取本地敏感配置。
- 先保证容器内 `/health` 可访问；不在此步骤配置 Cloudflare Tunnel。
- Python 镜像优先使用稳定版本，避免本机 Python 3.14 带来的第三方兼容风险。

## Checklist

- [x] 检查现有 Docker/部署配置
- [x] 新增 `.dockerignore`
- [x] 新增 `Dockerfile`
- [x] 新增 `docker-compose.yml`
- [x] 构建镜像并启动容器
- [x] 验证容器 `/health`
- [x] 记录运行方式和后续 Cloudflare Tunnel 入口

## Review

- 已新增 `.dockerignore`，排除 `.env`、`.venv`、缓存、图片、Excel、DMG、HTML 报告等不应进入镜像的文件。
- 已新增 `Dockerfile`，基于 `python:3.12-slim` 安装依赖并用 uvicorn 运行 `main:app`。
- 已新增 `docker-compose.yml`，服务名 `data-agent`，镜像名 `data-agent:local`，容器名 `data-agent`，通过 `env_file: .env` 注入配置。
- 宿主机 `8000` 已被 `tk_video2-analyzer-1` 占用，`8001` 也被另一个本机 Python 服务占用；为避免影响其他项目，本项目最终映射为 `8010:8000`。
- `docker compose build` 成功，构建上下文约 218KB，`.dockerignore` 生效。
- `docker compose up -d` 成功，容器 `data-agent` 状态 healthy。
- 宿主验证通过：`curl http://127.0.0.1:8010/health` 返回 `{"status":"ok","service":"shu-tan"}`。
- 容器内测试通过：`docker compose exec -T data-agent python -m pytest -q` 返回 9 passed，1 个 Starlette/FastAPI TestClient 上游弃用 warning。
- 容器内数据库连通性通过：`SELECT 1 AS ok` 成功。
- 容器内 DeepSeek 连通性通过：测试消息返回 `OK`。
- 后续 Cloudflare Tunnel 应转发到 `http://localhost:8010`，飞书事件订阅 URL 使用 tunnel 域名加 `/feishu/webhook`。

---

# Cloudflare Tunnel Compose 配置计划

## Spec

目标：把用户提供的 Cloudflare Tunnel token 写入本地 `.env`，并在 `docker-compose.yml` 中新增 `cloudflared` 服务，使公网 tunnel 与 `data-agent` 容器运行在同一个 Docker 网络中。

边界：
- 不在回复中展示 tunnel token。
- `.env` 仍由 `.dockerignore` 排除，不进入镜像。
- Cloudflare Dashboard 的 Public Hostname 服务地址需要与容器网络匹配，推荐指向 `http://data-agent:8000`。
- 配置后重启 compose，并验证 `data-agent` 本地健康检查与 `cloudflared` 日志状态。

## Checklist

- [x] 将 Cloudflare Tunnel token 写入 `.env`
- [x] 更新 `.env.example` 增加占位键
- [x] 更新 `docker-compose.yml` 增加 `cloudflared` 服务
- [x] 重启 compose 服务
- [x] 验证 `data-agent` 和 `cloudflared` 状态

## Review

- 已将 Cloudflare Tunnel token 写入本地 `.env` 的 `CLOUDFLARED_TOKEN`。
- 已在 `.env.example` 增加 `CLOUDFLARED_TOKEN=` 占位。
- 已在 `docker-compose.yml` 增加 `cloudflared` 服务，使用 `cloudflare/cloudflared:latest` 和 token 运行 tunnel。
- `docker compose up -d` 成功，`data-agent` 状态 healthy，`data-agent-cloudflared` 正常运行。
- `cloudflared` 日志显示 connectivity pre-check 全部 PASS，并注册了 4 条 tunnel connection。
- 宿主健康检查通过：`curl http://127.0.0.1:8010/health` 返回 `{"status":"ok","service":"shu-tan"}`。
- Cloudflare Public Hostname 的 Service 应填写：Type 选 `HTTP`，URL 填 `data-agent:8000`；如果在 Docker 外运行 tunnel 才使用 `localhost:8010`。

---

# 飞书群聊无响应二次排查计划

## Spec

目标：确认群聊 @ 无响应是飞书应用后台未推送事件、事件格式/加密不匹配、权限未开通，还是服务端处理失败；给出飞书开放平台需要逐项核对的配置。

边界：
- 不迁移到 SDK，除非确认当前 HTTP webhook 模式无法满足；SDK 只是封装 token/验签/事件处理，不是接收事件的必要条件。
- 不泄露 `.env` 密钥和 tunnel token。
- 先用日志和公网模拟请求判断事件是否到达服务。

## Checklist

- [x] 查看 `data-agent` 与 `cloudflared` 最新日志
- [x] 用公网模拟飞书消息事件确认服务会处理 POST
- [x] 对照飞书应用后台配置列出核对项
- [x] 必要时补充服务端日志方便继续定位

## Review

- 最近日志中没有真实飞书 @ 消息产生的 `POST /feishu/webhook`，只有手动 challenge 测试的 POST；因此当前最可能是飞书开放平台应用配置没有把消息事件推到服务端。
- Cloudflare Tunnel 与 FastAPI 均正常：公网 challenge POST 可返回 200，`/health` 正常。
- 当前项目使用 Request URL 回调模式，不使用 SDK 长连接模式；飞书后台事件订阅方式必须选择 Request URL/请求网址，而不是长连接。
- 飞书后台需核对：机器人能力启用、事件 `im.message.receive_v1` 已订阅、接收群聊 @ 消息与发送消息权限已申请并发布生效、应用已安装到租户、机器人已加入目标群。
- 事件加密建议先关闭；如果后台启用 Encrypt Key，当前代码不会解密 `encrypt` 包体，需要补解密逻辑或改用 SDK。
- 已新增安全调试日志，只打印 webhook keys、是否 challenge/encrypt、event_type、message_id、chat_type、message_type、是否提取到文本，不打印消息内容或密钥。
- 用户再次在群里 @ 机器人后，服务端仍未出现新的 `POST /feishu/webhook`；因此当前问题仍定位在飞书应用后台未向 Request URL 推送群聊 @ 事件。
- 后续飞书事件推送记录显示 `im.message.receive_v1` SUCCESS，服务端日志显示收到的请求为 `{"encrypt": ...}`，说明事件加密已开启。
- 已接入飞书 SDK 的 `AESCipher`，当 webhook 收到 `encrypt` 字段时会用 `FEISHU_ENCRYPT_KEY` 解密后再处理事件。
- `.env` 当前 `FEISHU_ENCRYPT_KEY` 与 `FEISHU_VERIFICATION_TOKEN` 均已配置。
- `.venv/bin/python -m pytest -q` 通过：9 passed，2 个上游弃用 warning。
- `docker compose up -d --build` 已完成，容器已重启并加载加密事件解密逻辑。

---

# 飞书群聊话题回复行为调整计划

## Spec

目标：让机器人在群聊中只响应明确 @ 自己的消息，并在首次响应时开启/进入一个飞书话题；后续只处理这个话题内的消息，避免监听和打断整个群聊。

边界：
- 单聊仍可直接响应。
- 群聊普通消息如果没有 @ 机器人，直接忽略。
- 群聊中 @ 机器人后，用回复原消息的方式发送“正在查询”，让飞书创建/进入话题。
- 后续群聊话题消息只在该话题已由机器人激活时处理；普通群消息仍需 @。
- 当前会话/活跃话题仍是内存态，容器重启会丢失。

## Checklist

- [x] 增加机器人身份查询/缓存
- [x] 增加群聊 @ 机器人识别
- [x] 调整群聊回复为原消息话题内回复
- [x] 限制只处理机器人激活的话题
- [x] 增加/更新测试
- [x] 重建容器并验证

## Review

- 已在 `feishu.sender` 增加 `get_bot_open_id()`，通过 `/open-apis/bot/v3/info` 获取并缓存机器人 `open_id`。
- 已调整 `feishu.webhook` 路由行为：群聊普通消息必须 @ 当前机器人；未 @ 的普通群消息直接忽略。
- 群聊首次 @ 机器人后，会把该消息 ID 或已有 thread ID 记录为活跃话题；后续只处理该活跃话题内消息。
- 群聊回复从“向群聊发新卡片”改为 `reply_to_message(..., reply_in_thread=True)`，让飞书在原消息下创建/进入话题。
- 单聊仍保持直接响应。
- 已新增 `tests/test_feishu_webhook.py`，覆盖：未 @ 忽略、@ 机器人激活话题、只处理活跃话题、单聊继续可用。
- `.venv/bin/python -m pytest -q` 通过：13 passed，2 个上游弃用 warning。
- `docker compose up -d --build` 已完成，`data-agent` 状态 healthy。
- 宿主验证通过：`curl http://127.0.0.1:8010/health` 返回 `{"status":"ok","service":"shu-tan"}`。
- 容器内话题路由测试通过：4 passed，2 个上游 warning。

---

# 飞书结果展示体验修复计划

## Spec

目标：修复飞书查询结果展示中的三个问题：图表中文乱码、Markdown 表格在飞书卡片中不正确渲染、执行 SQL 默认折叠并由用户点击后查看。

边界：
- 不改 SQL 生成和查询逻辑。
- 飞书当前不支持已尝试过的 `collapse` block；SQL 折叠改为默认隐藏，点击“查看 SQL”后发送 SQL 卡片。
- 表格不再依赖飞书 Markdown 表格语法，改用卡片 `column_set` 结构化渲染。
- 容器内安装中文字体，优先使用 Noto CJK，避免 matplotlib 中文缺字。

## Checklist

- [x] Docker 镜像安装中文字体
- [x] matplotlib 字体配置改为 Noto CJK 优先
- [x] 飞书结果表格改为结构化卡片列
- [x] SQL 默认隐藏并通过按钮查看
- [x] 更新卡片回调处理 `show_sql`
- [x] 增加/更新测试
- [x] 重建容器并验证

## Review

- Docker 镜像已安装 `fonts-noto-cjk`，容器内 matplotlib 可用字体包含 `Noto Sans CJK SC`。
- `visualization.chart` 已改为运行时动态选择已安装中文字体；容器内验证 `plt.rcParams['font.family']` 为 `['Noto Sans CJK SC', 'DejaVu Sans', 'sans-serif']`。
- 容器内生成中文图表成功，不再出现中文 glyph 缺失或 PingFang/Arial 字体缺失日志。
- 结果卡片表格从 Markdown 表格改为飞书卡片 `column_set` 结构化渲染，避免飞书不支持 GFM 表格导致显示异常。
- 执行 SQL 默认不再展示；结果卡片增加“查看 SQL”按钮，点击后通过 `show_sql` 回调发送 SQL 卡片。
- 因飞书此前不支持 `collapse` block，当前实现为“默认隐藏 + 点击按钮显示 SQL”，而不是使用不兼容的原生折叠 block。
- 已新增/更新卡片测试，覆盖结构化表格、SQL 默认隐藏、`show_sql` 按钮和 SQL 卡片。
- `.venv/bin/python -m pytest -q` 通过：15 passed，2 个上游 warning。
- 容器内 `python -m pytest -q` 通过：15 passed，3 个上游 warning。
- `docker compose up -d --build` 已完成，`data-agent` 状态 healthy，`curl http://127.0.0.1:8010/health` 正常。

---

# 项目冗余内容清理计划

## Spec

目标：清理项目中可安全删除的冗余内容，降低目录噪声和构建/协作干扰。

边界：
- 只自动删除可再生成的缓存、编译产物、系统临时文件。
- 不自动删除业务数据、Excel、HTML 报告、DMG、方案文档、`.env`、`postgresql.env`。
- 对可能有价值但疑似冗余的大文件，只列出候选并等待用户确认。
- 清理后运行测试和健康检查，确认项目仍可用。

## Checklist

- [x] 盘点冗余/大文件候选
- [x] 删除安全缓存和编译产物
- [x] 删除未被代码引用的 `artifacts/`
- [x] 验证测试与容器状态
- [x] 记录保留/候选删除项

## Review

- `artifacts/` 中只有本地 Excel、旧 HTML 报告、DMG 安装包和系统文件，项目运行时代码、脚本、测试均未引用。
- 已删除 `artifacts/`，释放约 235MB。
- 已同步 README 项目结构，避免继续展示已删除目录。
- 本地测试通过：`.venv/bin/python -m pytest -q` 为 15 passed。
- SQL 回归通过：`.venv/bin/python scripts/validate_business_sql_cases.py` 为 10 passed。
- Docker 服务健康：`http://127.0.0.1:8010/health` 返回 `{"status":"ok","service":"shu-tan"}`，`data-agent` 状态 healthy。

---

# 项目标准架构重整计划

## Spec

目标：将当前项目整理为更规范、优雅、可维护的 Python 服务架构，明确应用代码、测试、脚本、文档、数据样例、运行配置的边界。

目标结构：

- `src/data_agent/`：应用主包，包含 FastAPI app、配置、Agent、飞书、会话、可视化模块。
- `src/data_agent/data_catalog/`：运行时需要加载的 Data Catalog。
- `tests/`：测试代码，导入 `data_agent.*`。
- `scripts/`：运维/验证脚本。
- `docs/`：方案文档、分析文档、历史报告说明。
- 根目录保留：`Dockerfile`、`docker-compose.yml`、`requirements.txt`、`.env.example`、`AGENTS.md`、`todo.md`、`lessons.md`。

边界：
- 不删除 `.env`、`postgresql.env`；业务 Excel、HTML、DMG 若确认未被项目引用则删除。
- 保持 Docker 服务、Cloudflare Tunnel 和飞书 webhook 入口可用。
- 避免引入新框架或大规模业务逻辑改写；本次主要是路径、导入和运行入口整理。
- 重构后必须跑测试、容器构建和健康检查。

## Checklist

- [x] 创建标准目录结构
- [x] 移动应用代码到 `src/data_agent/`
- [x] 移动 Data Catalog 到应用包内
- [x] 更新导入路径、脚本和测试
- [x] 整理 docs 并删除未引用 artifacts
- [x] 更新 Dockerfile 与运行入口
- [x] 清理缓存产物
- [x] 运行本地测试
- [x] 重建容器并验证健康检查

## Review

- 应用代码已迁移到 `src/data_agent/`，测试、脚本和 Docker 入口均改为导入/启动 `data_agent.*`。
- Data Catalog 已随运行时包移动到 `src/data_agent/data_catalog/`。
- 文档集中到 `docs/`；未被代码、脚本、测试引用的 `artifacts/` 已删除。
- 已新增 `pyproject.toml` 配置 pytest 的 `pythonpath`，本地开发可直接运行 `data_agent.*` 导入。
- 本地验证已通过：`.venv/bin/python -m pytest -q` 为 15 passed，`.venv/bin/python scripts/validate_business_sql_cases.py` 为 10 passed。
- Docker 已按新入口 `data_agent.main:app` 重建，`data-agent` 容器状态 healthy，宿主机 `8010` 健康检查正常。

## Checklist

- [x] 盘点项目内文件
- [x] 阅读 `AGENTS.md`
- [x] 阅读 `数探机器人完整实施方案.md`
- [x] 检查 `postgresql.env` 配置结构
- [x] 确认 `lessons.md` 当前为空，暂无用户纠错需要记录

## Review

- 当前目录不是 git 仓库，无法用 git diff/status 做版本对比。
- 当前项目尚未包含实际 Python/FastAPI 代码，只包含实施方案、推进规则、数据库连接配置和空白任务/经验文件。
- `postgresql.env` 包含真实数据库连接信息，后续回复和文档中不应泄露具体密码。
- 后续任何非平凡任务都应先在本文件写可检查计划，执行时逐项更新，完成后补充 Review。

---

# 本地 MVP 实现计划

## Spec

目标：把当前方案文档推进为可运行的本地 FastAPI 项目骨架，支持健康检查、飞书 Webhook 接入、DeepSeek SQL 生成封装、PostgreSQL 只读查询、安全校验、会话记忆、图表生成和基础自动化验证。

边界：
- 不把真实凭证写入提交型模板文件。
- 不主动连接真实飞书或 DeepSeek，除非后续明确提供并要求联调。
- 数据库连接配置从 `.env` / 环境变量读取；现有 `postgresql.env` 只作为人工参考，不直接导入源码。
- 先实现本地可测 MVP，后续再补 Redis、生产部署、完整 Data Catalog。

## Checklist

- [x] 创建项目结构和依赖文件
- [x] 实现配置加载与 `.env.example`
- [x] 实现 Agent、SQL 执行、会话、图表、飞书模块
- [x] 增加 Data Catalog starter 文档
- [x] 增加基础测试覆盖 SQL 安全、表格输出、健康检查
- [x] 运行验证命令并记录结果

## Review

- 已创建可运行 FastAPI MVP：`main.py`、配置、Agent、SQL 执行、会话、飞书、图表模块。
- 已新增 Data Catalog starter：系统规则、orders/products/advertising 表文档、跨表 JOIN 规则。
- 已新增基础测试：SQL 安全校验、Markdown 表格输出、图表列选择、健康检查。
- 依赖从方案中的旧固定版本调整为兼容区间；本机只有 Python 3.14，旧版 `psycopg2-binary==2.9.9` 和 `matplotlib==3.9.0` 无法可靠安装。
- 数据库驱动改为 `psycopg` v3，连接层仍保持只读查询行为，并设置 `default_transaction_read_only=on`。
- `python -m compileall agent feishu session visualization tests config.py main.py` 通过。
- `python -m pytest -q` 通过：7 passed，1 个 FastAPI TestClient 的上游弃用 warning。
- 已启动本地服务并验证 `GET /health` 返回 `{"status":"ok","service":"shu-tan"}`。

---

# 真实数据库 Data Catalog 落地计划

## Spec

目标：连接现有 PostgreSQL，盘点真实表结构、字段、注释、约束、索引和样例值，把业务含义沉淀到 `data_catalog/`，让 Agent 生成 SQL 时基于真实表字段，而不是示例 `orders/products/advertising`。

边界：
- 不在回复、文档或代码里泄露数据库密码。
- 只做只读结构和样例查询。
- 对无法从数据库注释确认的字段含义，明确标注为“根据字段名/样例值推断”，不伪装成确定业务口径。
- 优先落实常用查询能力：指标、维度、时间字段、过滤条件、JOIN 规则、安全限制。

## Checklist

- [x] 更新 `lessons.md`，记录 todo/lessons 同步提醒
- [x] 盘点数据库 schema、表、字段、类型、注释
- [ ] 盘点主键、外键、索引和行数估算
- [ ] 抽样查看关键表字段值，辅助理解业务含义
- [ ] 重写 `data_catalog/` 为真实数据库版本
- [ ] 运行验证并记录结果

## Review

待完成后补充。

---

# Innerbrightness 重点表 SQL 能力落地计划

## Spec

用户明确指定重点表范围，后续 Data Catalog 只优先围绕以下 Innerbrightness 表落地：

- `amazon_3p_amazon_fulfilled_shipments_innerbrightness`
- `amazon_3p_fba_inventory_planning_innerbrightness`
- `amazon_3p_fba_returns_innerbrightness`
- `amazon_3p_inventory_health_innerbrightness`
- `amazon_3p_inventory_innerbrightness`
- `amazon_3p_orders_innerbrightness`
- `amazon_3p_sales_and_traffic_innerbrightness`
- `amazon_ads_sb_campaign_placement_innerbrightness`
- `amazon_ads_sb_campaigns_innerbrightness`
- `amazon_ads_sb_purchased_product_innerbrightness`
- `amazon_ads_sb_search_term_innerbrightness`
- `amazon_ads_sb_targeting_innerbrightness`
- `amazon_ads_sp_advertised_product_innerbrightness`
- `amazon_ads_sp_campaign_placement_innerbrightness`
- `amazon_ads_sp_campaigns_innerbrightness`
- `amazon_ads_sp_purchased_product_innerbrightness`
- `amazon_ads_sp_search_term_innerbrightness`
- `amazon_ads_sp_targeting_innerbrightness`
- `amazon_replenishment_metrics_innerbrightness`

边界：
- 不再把泛 Amazon 全库表族作为当前 Catalog 主体。
- 优先从系统目录读取字段和类型；如果当前数据库用户无 SELECT 权限，则不强行样例查询。
- 字段含义分三类写入：Amazon 报表标准含义、字段名推断含义、无法确认待补充。

## Checklist

- [x] 同步记录本次范围纠偏到 `lessons.md`
- [x] 获取 19 张表字段、类型、注释、估算行数
- [x] 获取 19 张表索引、主键、外键和权限状态
- [x] 尝试轻量抽样/日期范围查询，记录是否有 SELECT 权限
- [x] 基于 19 张表重写 `data_catalog/`
- [x] 运行验证并补充 Review

## Review

- 已将 Data Catalog 从通用示例表改为 Innerbrightness 重点表专用。
- 当前账号可 SELECT 的重点表：`amazon_3p_inventory_innerbrightness`、`amazon_3p_orders_innerbrightness`、`amazon_3p_sales_and_traffic_innerbrightness`、全部 SP/SB 广告重点表。
- 当前账号无 SELECT 权限的重点表：`amazon_3p_amazon_fulfilled_shipments_innerbrightness`、`amazon_3p_fba_inventory_planning_innerbrightness`、`amazon_3p_fba_returns_innerbrightness`、`amazon_3p_inventory_health_innerbrightness`、`amazon_replenishment_metrics_innerbrightness`。
- 已明确 SP 与 SB 字段差异：SP 默认 `cost/sales14d/purchases14d`；SB campaign/search/targeting 默认 `cost/sales/purchases`；SB purchased product 用 `sales14d/orders_clicks14d/units_sold14d` 且不能单独算 ACoS。
- 已验证代表性 SQL 可执行：2026-05 订单销售额、Business Report 销售流量、SP 汇总、SB 汇总、库存快照均成功返回。
- `python -m compileall agent feishu session visualization tests config.py main.py` 通过。
- `python -m pytest -q` 通过：8 passed，1 个 FastAPI TestClient 上游弃用 warning。

---

# 业务问答测试集与 LLM 配置计划

## Spec

目标：落实用户同意的第 2、3 项：创建 Innerbrightness 真实业务问题测试集，并建立可回归的 SQL 校验框架；同时创建本地 `.env`，集中存放飞书、DeepSeek/LLM、PostgreSQL 配置。

边界：
- `.env` 是本地敏感配置文件，不提交、不在回复中展示真实密码。
- LLM API Key 先留空占位，等用户填入后再做真实 LLM 生成联调。
- 当前阶段先做“期望 SQL 与规则校验”的确定性回归测试；LLM 输出回归在 API Key 配好后接入。
- 剩余 5 张表权限预计 2-3 小时后开通，先把无权限表的测试用例标注为 pending/permission_required。

## Checklist

- [x] 创建本地 `.env`
- [x] 新增业务问答测试集
- [x] 新增 SQL 回归校验脚本/测试
- [x] 覆盖订单、Business Report、SP、SB、TACOS、库存、无权限表待授权场景
- [x] 运行验证并补充 Review

## Review

- 已创建本地 `.env`，包含飞书、DeepSeek/LLM、PostgreSQL、应用配置；`.env` 已被 `.gitignore` 忽略。
- `DEEPSEEK_API_KEY` 目前留空，等待用户填入后再做真实 LLM 生成联调。
- 已新增 [evals/innerbrightness_business_questions.json](/Users/ethan/data_agent/evals/innerbrightness_business_questions.json:1)，覆盖 10 个业务问题：订单、Business Report、SP、SB、SP 搜索词、SB 搜索词、TACOS、库存、FBA 退货待授权、Subscribe & Save 待授权。
- 已新增 [scripts/validate_business_sql_cases.py](/Users/ethan/data_agent/scripts/validate_business_sql_cases.py:1)，支持离线规则校验和 `--execute` 数据库实跑。
- 已新增 [tests/test_business_sql_regression.py](/Users/ethan/data_agent/tests/test_business_sql_regression.py:1)，防止测试集 SQL 漂移到错误表/字段/口径。
- 第一次实跑发现 SP double precision 比率 `ROUND(..., 4)` 类型问题，已改为显式 numeric cast，并同步更新 Catalog。
- `python -m pytest -q` 通过：9 passed，1 warning。
- `python scripts/validate_business_sql_cases.py` 通过：10 passed，0 failed。
- `python scripts/validate_business_sql_cases.py --execute` 通过：ready case 全部数据库执行成功，permission_required case 只做规则校验。
