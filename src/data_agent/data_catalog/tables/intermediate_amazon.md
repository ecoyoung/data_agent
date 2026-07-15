# intermediate_amazon_ 中间表总则

<!-- AI_HINT: canonical_source=intermediate_amazon_% multi_brand=true -->

`intermediate_amazon_` 开头的表/视图是当前数探的主数据源，覆盖多个品牌、店铺、站点和 Amazon 报表域。旧的 Innerbrightness 专用表只作为历史参考；除非用户明确要求旧表名，否则所有业务 SQL 都优先使用中间表。

## 命名关系

- 表名模式通常是：`intermediate_amazon_<report_family>_<brand_or_store>[_<market>]_view`。
- 末尾 token 多数表示品牌、客户、店铺或市场，例如 `innerbrightness`、`belliwelli`、`blueland`、`brumate`、`vp_us`、`beekeeper_ca`。
- 如果品牌/店铺在表名中已经唯一确定，不要再强行套旧的 `customer='innerbrightness'` 过滤。
- 如果表内存在 `brand`、`customer`、`customer_name`、`country`、`country_code`、`profile_name`，可按用户要求补充过滤。
- 多品牌汇总要用同一报表族下多个品牌表 `UNION ALL` 后再聚合，不能把不同粒度表直接 JOIN。

## 主要表族

- `intermediate_amazon_3p_orders_*_view`：3P/Seller 订单汇总。常用指标 `ordered_revenue`、`ordered_units`、`order_items`、`shipped_revenue`，常用维度 `report_date`、`sku`、`asin`、`country_code`、`customer_name`。
- `intermediate_amazon_3p_sales_and_traffic_*_view`：Business Report 销售与流量。常用指标 `salesbyasin_orderedproductsales_amount`、`salesbyasin_unitsordered`、`trafficbyasin_sessions`、`trafficbyasin_pageviews`。
- `intermediate_amazon_ams_campaigns_*_view`：AMS Campaign 汇总。常用指标 `ams_spend`、`ams_sales`、`ams_orders`、`ams_units`、`ams_impression`、`ams_click`、`ams_acos`、`ams_roas`。
- `intermediate_amazon_ams_advertised_product_*_view`：AMS advertised product ASIN/SKU 粒度。
- `intermediate_amazon_ams_search_term_*_view`：AMS 搜索词粒度。
- `intermediate_amazon_ams_targeting_*_view`：AMS targeting/keyword/ASIN 定向粒度。
- `intermediate_amazon_ams_campaigns_placement_*_view`：AMS placement 粒度。
- `intermediate_amazon_dsp_*_view`：Amazon DSP 报表，常用指标以 `dsp_` 开头。
- `intermediate_amazon_fba_returns_*_view`：FBA 退货。
- `intermediate_amazon_fba_inventory_days_*_view`：FBA 库存覆盖天数。

## 指标口径

- 用户只问“销售额/销售/销量”且没有 Business Report、Sessions、流量、转化率或广告上下文时，默认使用订单表；销售额用 `SUM(ordered_revenue)`，销量用 `SUM(ordered_units)`，订单商品项数用 `SUM(order_items)`。
- Business Report 销售额用 `SUM(salesbyasin_orderedproductsales_amount)`；Sessions 用 `SUM(trafficbyasin_sessions)`；转化率用 `SUM(salesbyasin_unitsordered) / NULLIF(SUM(trafficbyasin_sessions), 0)`。
- AMS 广告花费用 `SUM(ams_spend)`；广告销售用 `SUM(ams_sales)`；广告订单用 `SUM(ams_orders)`；ACoS 用 `SUM(ams_spend) / NULLIF(SUM(ams_sales), 0)`；ROAS 用 `SUM(ams_sales) / NULLIF(SUM(ams_spend), 0)`。
- DSP 花费用 `SUM(dsp_cost)`；DSP 销售优先用 `SUM(dsp_total_sales)` 或按用户指定用 `SUM(dsp_sales)`；DSP ROAS 用销售额除以花费。
- PostgreSQL `ROUND(expr, n)` 的 `expr` 必须整体 `::numeric`，例如 `ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4)`。

## 日期和安全

- 大多数中间表用 `report_date`，退货表用 `return_date`；日期字段类型见结构化 Catalog。
- 所有事实查询必须带明确日期过滤。
- 月份问题默认按月聚合成一行，例如 `to_char(report_date, 'YYYY-MM') AS month` 并 `GROUP BY 1`；不要写 `GROUP BY month`。只要用户明确要求“趋势/走势/每天/按日/每日趋势”，就按 `report_date` 输出完整日明细。
- 不查询 PII 或客户评论类字段；`customer_comments` 属于敏感/低价值字段，默认不要展示。
- 使用结构化 Catalog 中的实际字段名，不要把旧原始表字段名套到中间表上。
