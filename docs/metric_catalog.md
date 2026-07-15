# 指标口径 Catalog

本文档记录当前数探默认指标口径。所有业务 SQL 默认使用 `intermediate_amazon_` 中间表；旧 `amazon_*_innerbrightness` 专用表不再作为默认数据源。

## 总原则

- 主数据源是 `intermediate_amazon_` 中间表，覆盖多品牌、多店铺、多站点。
- 品牌/店铺优先从表名后缀识别，例如 `intermediate_amazon_3p_orders_belliwelli_view`、`intermediate_amazon_ams_campaigns_innerbrightness_view`。
- 表内如有 `brand`、`customer`、`customer_name`、`country`、`country_code`、`profile_name`，再按用户指定条件过滤。
- 多品牌/全部店铺问题使用同一表族多张表 `UNION ALL` 标准化后聚合。
- 不同粒度表不能明细直接 JOIN；必须先聚合到共同粒度再 JOIN。
- 所有事实查询必须带业务日期过滤，常见字段是 `report_date` 或 `return_date`。
- 用户问某个月份的数据，例如“2026年6月/6月份/2026-06”，且没有明确说“趋势/走势/每天/按日/每日趋势”，默认输出月度汇总一行：`to_char(report_date, 'YYYY-MM') AS month`，`GROUP BY 1`。不要把 30 天明细作为默认结果。
- 月度聚合不要使用 `GROUP BY month` 别名分组；使用 `GROUP BY 1` 或 `GROUP BY to_char(report_date, 'YYYY-MM')`。
- 只要用户明确要求“趋势/走势/每天/每日/按日/daily”，就按 `report_date` 分组输出日明细，按日期升序，用于折线图。
- 比率必须防除零：`NULLIF(denominator, 0)`。
- PostgreSQL `ROUND(expr, n)` 的 `expr` 必须整体转为 `numeric`，例如 `ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4)`。

## 订单与销售

| 指标 | 默认口径 | 中间表族 | SQL 表达式 |
| --- | --- | --- | --- |
| 订单销售额 | 中间订单汇总销售额 | `intermediate_amazon_3p_orders_*_view` | `SUM(ordered_revenue)` |
| 订单销量 | 中间订单汇总件数 | `intermediate_amazon_3p_orders_*_view` | `SUM(ordered_units)` |
| 订单商品项数 | 中间订单 item 数 | `intermediate_amazon_3p_orders_*_view` | `SUM(order_items)` |
| Business Report 销售额 | Ordered Product Sales | `intermediate_amazon_3p_sales_and_traffic_*_view` | `SUM(salesbyasin_orderedproductsales_amount)` |
| Business Report 销量 | Units Ordered | `intermediate_amazon_3p_sales_and_traffic_*_view` | `SUM(salesbyasin_unitsordered)` |

## Business Report 流量转化

| 指标 | 默认口径 | SQL 表达式 |
| --- | --- | --- |
| Sessions | ASIN sessions | `SUM(trafficbyasin_sessions)` |
| Page Views | ASIN page views | `SUM(trafficbyasin_pageviews)` |
| 转化率 | Units Ordered / Sessions | `ROUND((SUM(salesbyasin_unitsordered) / NULLIF(SUM(trafficbyasin_sessions), 0))::numeric, 4)` |
| Buy Box | Buy Box percentage | 按问题指定；不要默认简单 AVG，必要时说明需复核加权口径 |

禁止默认使用 `AVG(trafficbyasin_unitsessionpercentage)` 作为转化率。

## AMS 广告

AMS 中间表统一使用 `ams_*` 字段，不再区分旧原始 SP/SB 表的 `sales14d`、`purchases14d`、`sales`、`cost`。

| 指标 | 默认口径 | 中间表族 | SQL 表达式 |
| --- | --- | --- | --- |
| 广告花费 | AMS spend | `intermediate_amazon_ams_*_view` | `SUM(ams_spend)` |
| 广告销售额 | AMS attributed sales | `intermediate_amazon_ams_*_view` | `SUM(ams_sales)` |
| 广告订单数 | AMS orders | `intermediate_amazon_ams_*_view` | `SUM(ams_orders)` 或表内订单字段 |
| 广告销量 | AMS units | `intermediate_amazon_ams_*_view` | `SUM(ams_units)` |
| 曝光 | AMS impressions | `intermediate_amazon_ams_*_view` | `SUM(ams_impression)` |
| 点击 | AMS clicks | `intermediate_amazon_ams_*_view` | `SUM(ams_click)` |
| ACoS | 花费 / 广告销售额 | `intermediate_amazon_ams_*_view` | `ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4)` |
| ROAS | 广告销售额 / 花费 | `intermediate_amazon_ams_*_view` | `ROUND((SUM(ams_sales) / NULLIF(SUM(ams_spend), 0))::numeric, 4)` |
| CTR | 点击 / 曝光 | `intermediate_amazon_ams_*_view` | `ROUND((SUM(ams_click) / NULLIF(SUM(ams_impression), 0))::numeric, 4)` |
| CPC | 花费 / 点击 | `intermediate_amazon_ams_*_view` | `ROUND((SUM(ams_spend) / NULLIF(SUM(ams_click), 0))::numeric, 4)` |

常见表族选择：

- Campaign 维度：`intermediate_amazon_ams_campaigns_*_view`
- Search term 维度：`intermediate_amazon_ams_search_term_*_view`
- Targeting 维度：`intermediate_amazon_ams_targeting_*_view`
- Advertised product ASIN/SKU：`intermediate_amazon_ams_advertised_product_*_view`
- Placement：`intermediate_amazon_ams_campaigns_placement_*_view`

## DSP 广告

DSP 中间表统一使用 `dsp_*` 字段。注意不是所有 DSP 表都有花费字段，例如 `dsp_product` 表有商品销售/购买字段，但 `dsp_cost` 在 order funnel 等表中更常见。

| 指标 | 默认口径 | 中间表族 | SQL 表达式 |
| --- | --- | --- | --- |
| DSP 花费 | DSP cost | `intermediate_amazon_dsp_order_funnel_*_view` 等含 `dsp_cost` 的表 | `SUM(dsp_cost)` |
| DSP 销售额 | Total sales 优先 | `intermediate_amazon_dsp_*_view` | `SUM(dsp_total_sales)`，如用户指定可用 `SUM(dsp_sales)` |
| DSP 购买数 | Total purchases 优先 | `intermediate_amazon_dsp_*_view` | `SUM(dsp_total_purchases)`，如用户指定可用 `SUM(dsp_purchases)` |
| DSP ROAS | 销售额 / 花费 | 含 `dsp_cost` 与销售字段的 DSP 表 | `ROUND((SUM(dsp_total_sales) / NULLIF(SUM(dsp_cost), 0))::numeric, 4)` |

## 退货与库存

| 指标 | 默认口径 | 中间表族 | SQL 表达式 |
| --- | --- | --- | --- |
| FBA 退货数量 | return units | `intermediate_amazon_fba_returns_*_view` | `SUM(return_units)` |
| 退货原因 | reason 维度 | `intermediate_amazon_fba_returns_*_view` | `GROUP BY reason` |
| 库存覆盖 | inventory days | `intermediate_amazon_fba_inventory_days_*_view` | 按实际字段和 Catalog 选择 |

`customer_comments` 等客户评论字段默认不展示。

## 跨域指标

| 指标 | 默认口径 | 计算方式 |
| --- | --- | --- |
| TACOS | AMS 花费 / 订单销售额 | 先聚合 `intermediate_amazon_ams_campaigns_*_view` 的 `SUM(ams_spend)`，再聚合对应品牌 `intermediate_amazon_3p_orders_*_view` 的 `SUM(ordered_revenue)`，按日期或品牌 JOIN |
| 广告销售占比 | AMS 广告销售 / 订单销售 | `SUM(ams_sales) / NULLIF(SUM(ordered_revenue), 0)`，需先按共同粒度聚合 |
| ASIN 广告与 BR 对比 | advertised ASIN vs BR ASIN | `advertised_asin = asin`，两边先按 ASIN/日期聚合 |

## 口径选择规则

- 用户只问“销售额/销售/销量”且没有 Business Report、Sessions、流量、转化率或广告上下文：默认订单中间表，销售额用 `SUM(ordered_revenue)`，不追问口径。
- 用户问 Sessions、Page Views、转化率：默认 Business Report 中间表。
- 用户问广告花费、ACoS、ROAS、CTR、CPC：默认 AMS 中间表；如果明确 DSP，则使用 DSP 中间表。
- 用户问“所有品牌/全部店铺”：使用同一表族多张表 `UNION ALL`。
- 用户未指定品牌/店铺且问题会影响结果范围：先追问品牌/店铺/站点。
