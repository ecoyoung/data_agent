# intermediate_amazon_ JOIN and Business SQL Rules

## Source Priority

- `intermediate_amazon_` 中间表是当前主数据源，覆盖多个品牌、店铺和站点。
- 旧 `amazon_*_innerbrightness` 专用表只作为历史参考；默认不要再查询这些旧表。
- 表名通常包含报表族和品牌/店铺 token。先选同一报表族下的目标品牌表，再写 SQL。

## Brand / Store / Market Rules

- 单品牌问题：优先选择表名中包含该品牌/店铺 token 的中间表，例如 Belli Welli 订单用 `intermediate_amazon_3p_orders_belliwelli_view`。
- Inner brightness 问题：使用 `*_innerbrightness_view` 中间表，而不是旧 `amazon_*_innerbrightness` 表。
- 多品牌/全部店铺问题：选择同一报表族下多个品牌表，先 `UNION ALL` 成标准列，再聚合。
- 市场可能出现在表名后缀（如 `_us`、`_ca`、`_uk`、`_eu`）或表内字段（`country_code`、`country`、`profile_name`）。用户指定站点时必须过滤或选择对应后缀表。
- 不要默认把所有问题过滤为 Innerbrightness；品牌不明确且会影响结果时，先追问。

## Granularity Rules

- `intermediate_amazon_3p_orders_*_view`：订单/销售汇总粒度，通常为 `report_date + sku + asin + country/customer`。
- `intermediate_amazon_3p_sales_and_traffic_*_view`：Business Report ASIN 日粒度，通常为 `report_date + asin + country/customer`。
- `intermediate_amazon_ams_campaigns_*_view`：AMS Campaign 日粒度。
- `intermediate_amazon_ams_advertised_product_*_view`：AMS 广告商品 ASIN/SKU 日粒度。
- `intermediate_amazon_ams_search_term_*_view`：AMS 搜索词日粒度。
- `intermediate_amazon_ams_targeting_*_view`：AMS targeting 日粒度。
- `intermediate_amazon_ams_campaigns_placement_*_view`：AMS placement 日粒度。
- `intermediate_amazon_dsp_*_view`：DSP 报表粒度随表族变化，通常以 `report_date + profile/order/product/audience` 为主。

不同粒度表不能明细直接 JOIN。必须先按共同维度聚合，例如 `date + asin`、`date + brand`、`date + campaign_id`，再 JOIN。

## Product Keys

- 订单中间表商品键：`asin`、`sku`。
- Business Report 中间表商品键：通常是 `asin`。
- AMS advertised product 商品键：`advertised_asin`、`advertised_sku`。
- DSP product 商品键：`asin`、`parent_asin`。

常用 ASIN JOIN：

```sql
orders.asin = business_report.asin
ads.advertised_asin = business_report.asin
dsp_product.asin = business_report.asin
```

## Sales and Ads Metrics

- Total order sales：`SUM(ordered_revenue)`。
- Business Report sales：`SUM(salesbyasin_orderedproductsales_amount)`。
- AMS ad sales：`SUM(ams_sales)`。
- AMS ad spend：`SUM(ams_spend)`。
- DSP spend：`SUM(dsp_cost)`。
- DSP sales：优先按用户口径选择 `SUM(dsp_total_sales)` 或 `SUM(dsp_sales)`。

## Cross-Domain Rules

- TACOS：同一品牌/店铺内，先聚合订单销售和 AMS 花费，再按日期或 ASIN JOIN，计算 `ams_spend / ordered_revenue`。
- 广告商品和 BR 对比：先把 `intermediate_amazon_ams_advertised_product_*_view` 聚合到 `advertised_asin`，再 JOIN Business Report 的 `asin`。
- 多品牌排行榜：每个品牌表 SELECT 出标准列 `brand_or_store, report_date, metric...`，`UNION ALL` 后统一聚合排序。

## Permission Notes

数据库中存在的 `intermediate_amazon_` 对象不等于当前应用账号都有 SELECT 权限。运行时会在 SQL 执行前用当前 DB 用户做实时权限预检；没有 SELECT 权限时直接返回权限错误，不进入 LLM retry。

结构化 Catalog 的 `select_permission=true` 是生成时快照；数据库授权变化后必须重新生成 Catalog，或依赖运行时权限预检兜底。当前内测账号可能只开放部分 scope（例如 Beekeeper 系列）。
