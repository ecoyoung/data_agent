# Lessons

- 用户明确提醒“todo 和 lessons 要同步更新”时，后续每个非平凡推进都必须先检查并同步这两个文件：`todo.md` 记录计划/进度/结果，`lessons.md` 记录用户纠正或流程偏差的防复发规则。
- 启动/检查服务时必须先用 `docker compose ps`、`docker ps` 和端口映射确认目标服务来源；本项目 Docker 对外端口是 `8010->8000`，不能直接假设 `127.0.0.1:8000` 就是 Data Detector，也不能在已有 Docker 服务时额外启动本地 uvicorn。
- 用户提供的参考 PDF/资料即使是未跟踪文件，也不能因“不是运行资产”擅自删除；除非用户明确说删除该资料。清理前应把参考资料和临时抽取物区分开，临时文件可删，用户资料默认保留。
- 可视化格式识别必须覆盖常见字段后缀，尤其 `_pct` / `_percentage`；`sales_mom_change_pct`、`units_mom_change_pct` 这类列虽然包含 sales/units，也必须优先按百分比展示，不能误判为金额或数量。
- 修复线上展示问题时，不能只跑本地测试；本项目服务运行在 Docker 容器中，代码修复后必须重建/重启容器并用容器内代码或健康检查验证，否则用户仍会看到旧行为。
- 当用户指定重点表范围时，必须立即收窄上下文和 Data Catalog 工作范围；不要继续围绕全库或示例表泛化推进。
- 当数据库账号权限从单品牌扩展为多品牌/多店铺时，必须重新识别主数据源和表族关系；不要沿用旧的 Innerbrightness 专用表假设。若用户确认中间表是最全数据源，应同步 Prompt、Catalog、SQL Checker、evals 和 few-shot 示例到 `intermediate_amazon_` 中间表。
- 用户纠正“销售额一般使用 ordered_revenue”后，通用“销售额/销售”不再追问订单/BR/广告口径；默认用 `intermediate_amazon_3p_orders_*_view` 的 `SUM(ordered_revenue)`。只有用户明确说 Business Report、sessions、流量、转化率或广告归因销售额时，才切到 BR/广告口径。
- 月份问题例如“2026年6月/6月份”默认要按月聚合输出 `2026-06` 一行总数据；只有用户明确说“每天/按日/daily/每日趋势”时才按 `report_date` 展开，避免 30 天明细被飞书表格只展示前 10 行。
- 用户问“趋势”时，即使只说“2026年6月份”，也表示要按时间维度展开；月内趋势必须按 `report_date` 输出完整日数据并优先展示折线图，不能月汇总成一行，也不能只展示前 10 天。
- 月度聚合 SQL 中 `to_char(report_date, 'YYYY-MM') AS month` 不能配 `GROUP BY month`；在当前 PostgreSQL/视图路径下会报 `report_date must appear in the GROUP BY clause`。必须用 `GROUP BY 1` 或 `GROUP BY to_char(report_date, 'YYYY-MM')`，并用 SQL Checker 拦截别名分组。
- 修复 SQL Checker 误判时，回归测试必须覆盖用户提供的完整原始 SQL，而不只覆盖简化后的理想 SQL；尤其要包含表别名、`COALESCE()`、类型转换、函数包裹和换行等 LLM 常见真实输出形态。
- 写项目计划书时，如果用户说“不要按照当前进度/已有基础”，不是要推翻文档框架，而是保留原框架，用从 0 启动项目的口径重写内容；不要把当前已完成能力写成既有前提。
- Catalog 中某些中间表日期字段是 `text`（例如 `intermediate_amazon_ams_advertised_product_*_view.report_date`），不能生成 `report_date = DATE 'YYYY-MM-DD'` 这类 text=date 比较；必须用 `report_date::date = DATE ...`，并在 SQL repair / Catalog hint / 回归测试中覆盖。
- 表名 scope 后缀（如 `_blueland_view`）已经限定品牌/店铺时，不要再猜 `brand = 'blueland'` 或 `customer = scope_token`；真实字段值可能大小写或格式不同（如 `Blueland`、`Blueland_US-US-US-US`）。只有用户明确给出字段值或 Catalog 有真实取值时才加 brand/customer 过滤，字符串过滤应优先用 `LOWER(field) = LOWER(value)`。
- 仅在 prompt/Catalog 中写“不要猜 brand/customer = scope token”不够；对中间表 scope 已限定的 SQL，要在执行前 repair 中移除 `brand/customer/customer_name/profile_name = '<scope token or alias>'` 这类重复过滤，防止大小写敏感或真实值格式差异导致空结果。
- 用户问 SP/SD/SB 或 `sp+sd`、`sp+sb` 时，广告中间表要用真实广告类型字段过滤；`ams_advertised_product_*` 表用 `LOWER(ams_type) IN (...)`，不能漏掉广告类型过滤，也不要幻觉 `campaign_type`。
- 可视化策略中的“双 y 轴”不能一概否定：通用自动图表应避免双轴，但当用户明确要求且字段组合固定、单位清晰时，可以作为专用 recipe 实现，例如销量柱图 + 销售额折线图，并必须用颜色绑定、轴标题和图例降低误读风险。
