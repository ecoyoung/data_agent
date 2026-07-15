# 高频查询模板

这些模板用于约束常见 Amazon 问法的 SQL 粒度和口径。模板优先级低于用户明确指定的字段/粒度，但高于临场猜测。

## 订单月汇总

适用：`2026年6月 销售额/销量/订单数/数据`，且没有“趋势/每天/按日”。

```sql
SELECT
    to_char(report_date, 'YYYY-MM') AS month,
    SUM(ordered_revenue) AS order_revenue,
    SUM(ordered_units) AS units,
    SUM(order_items) AS order_items
FROM intermediate_amazon_3p_orders_<scope>_view
WHERE report_date >= DATE '<month_start>'
  AND report_date < DATE '<next_month_start>'
  AND country_code = '<country_code>'
GROUP BY 1
ORDER BY 1;
```

规则：不要 `GROUP BY month`；不要按 `report_date` 展开；不要用 Business Report 销售额。

## 订单日趋势

适用：`销售额趋势/销量趋势/每天销售额/每日订单`。

```sql
SELECT
    report_date,
    SUM(ordered_revenue) AS order_revenue
FROM intermediate_amazon_3p_orders_<scope>_view
WHERE report_date >= DATE '<start_date>'
  AND report_date < DATE '<end_date>'
  AND country_code = '<country_code>'
GROUP BY report_date
ORDER BY report_date;
```

规则：必须返回完整日期序列；用于折线图；不要月汇总成一行。

## Business Report ASIN 排名

适用：`Business Report 销售额最高 ASIN`、同时问 `sessions/转化率/page views`。

```sql
SELECT
    asin,
    SUM(salesbyasin_orderedproductsales_amount) AS br_sales,
    SUM(salesbyasin_unitsordered) AS units,
    SUM(trafficbyasin_sessions) AS sessions,
    ROUND((SUM(salesbyasin_unitsordered) / NULLIF(SUM(trafficbyasin_sessions), 0))::numeric, 4) AS unit_session_rate
FROM intermediate_amazon_3p_sales_and_traffic_<scope>_view
WHERE report_date >= DATE '<start_date>'
  AND report_date < DATE '<end_date>'
  AND country_code = '<country_code>'
GROUP BY asin
ORDER BY br_sales DESC
LIMIT 20;
```

规则：转化率不要用 `AVG(trafficbyasin_unitsessionpercentage)`。

## AMS 排名

适用：`广告花费最多/ACoS/ROAS/campaign/search term/targeting/advertised ASIN 排名`。

```sql
SELECT
    <dimension>,
    SUM(ams_spend) AS spend,
    SUM(ams_sales) AS ad_sales,
    SUM(ams_orders) AS ad_orders,
    ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4) AS acos,
    ROUND((SUM(ams_sales) / NULLIF(SUM(ams_spend), 0))::numeric, 4) AS roas
FROM intermediate_amazon_ams_<family>_<scope>_view
WHERE report_date >= DATE '<start_date>'
  AND report_date < DATE '<end_date>'
GROUP BY <dimension>
ORDER BY spend DESC
LIMIT 20;
```

规则：花费用 `ams_spend`，广告销售用 `ams_sales`。

## AMS advertised ASIN 按广告类型汇总

适用：`每个产品 ASIN 的 SP/SD/SB 广告花费和销售额`、`sp+sd 广告商品表现`。

```sql
SELECT
    advertised_asin AS asin,
    ROUND(SUM(ams_spend)::numeric, 2) AS ad_spend,
    ROUND(SUM(ams_sales)::numeric, 2) AS ad_sales
FROM intermediate_amazon_ams_advertised_product_<scope>_view
WHERE report_date::date = DATE '<date>'
  AND country_code = '<country_code>'
  AND LOWER(ams_type) IN ('sp', 'sd')
GROUP BY advertised_asin
ORDER BY ad_spend DESC
LIMIT 20;
```

规则：产品 ASIN 粒度用 `advertised_asin`；SP/SD/SB 过滤用 `ams_type`；表名 `<scope>` 已经限定品牌/店铺，不要再猜 `brand = '<scope>'` 或 `customer = '<scope>'`。

## TACOS 趋势

适用：`TACOS 趋势/每日 TACOS`。

```sql
WITH total_sales AS (
    SELECT report_date, SUM(ordered_revenue) AS total_sales
    FROM intermediate_amazon_3p_orders_<scope>_view
    WHERE report_date >= DATE '<start_date>'
      AND report_date < DATE '<end_date>'
      AND country_code = '<country_code>'
    GROUP BY report_date
),
ad_spend AS (
    SELECT report_date, SUM(ams_spend) AS spend
    FROM intermediate_amazon_ams_campaigns_<scope>_view
    WHERE report_date >= DATE '<start_date>'
      AND report_date < DATE '<end_date>'
    GROUP BY report_date
)
SELECT
    s.report_date,
    s.total_sales,
    COALESCE(a.spend, 0) AS ad_spend,
    ROUND((COALESCE(a.spend, 0) / NULLIF(s.total_sales, 0))::numeric, 4) AS tacos
FROM total_sales s
LEFT JOIN ad_spend a ON a.report_date = s.report_date
ORDER BY s.report_date;
```

规则：订单销售额分母用 `ordered_revenue`；两边先按日期聚合再 JOIN。
