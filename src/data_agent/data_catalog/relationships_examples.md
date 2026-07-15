# intermediate_amazon_ Cross-Domain SQL Examples

Conditional companion to `relationships.md`. Loaded for intermediate-table
questions that need cross-domain aggregation, such as TACOS or multi-brand
rollups.

## Single-Brand TACOS

TACOS = AMS ad spend / total order sales. Use the same brand/store suffix for
orders and campaigns, aggregate first, then join.

```sql
WITH total_sales AS (
    SELECT
        report_date,
        SUM(ordered_revenue) AS total_sales
    FROM intermediate_amazon_3p_orders_belliwelli_view
    WHERE report_date >= DATE '2026-07-01'
      AND report_date <  DATE '2026-08-01'
      AND country_code = 'US'
    GROUP BY 1
),
ad_spend AS (
    SELECT
        report_date,
        SUM(ams_spend) AS ad_spend
    FROM intermediate_amazon_ams_campaigns_belliwelli_view
    WHERE report_date >= DATE '2026-07-01'
      AND report_date <  DATE '2026-08-01'
      AND country = 'US'
    GROUP BY 1
)
SELECT
    s.report_date,
    s.total_sales,
    COALESCE(a.ad_spend, 0) AS ad_spend,
    ROUND((COALESCE(a.ad_spend, 0) / NULLIF(s.total_sales, 0))::numeric, 4) AS tacos
FROM total_sales s
LEFT JOIN ad_spend a ON a.report_date = s.report_date
ORDER BY s.report_date;
```

## Multi-Brand Orders Rollup

For "all brands" questions, normalize the same report family with `UNION ALL`.

```sql
WITH orders AS (
    SELECT 'belliwelli' AS brand_scope, report_date, ordered_revenue, ordered_units
    FROM intermediate_amazon_3p_orders_belliwelli_view
    WHERE report_date >= DATE '2026-07-01'
      AND report_date <  DATE '2026-08-01'
    UNION ALL
    SELECT 'innerbrightness' AS brand_scope, report_date, ordered_revenue, ordered_units
    FROM intermediate_amazon_3p_orders_innerbrightness_view
    WHERE report_date >= DATE '2026-07-01'
      AND report_date <  DATE '2026-08-01'
)
SELECT
    brand_scope,
    SUM(ordered_revenue) AS sales,
    SUM(ordered_units) AS units
FROM orders
GROUP BY brand_scope
ORDER BY sales DESC;
```

## AMS Ads Summary

AMS intermediate tables standardize SP/SB-style campaign metrics as `ams_*`.

```sql
SELECT
    report_date,
    campaign_name,
    SUM(ams_spend) AS spend,
    SUM(ams_sales) AS ad_sales,
    SUM(ams_orders) AS ad_orders,
    SUM(ams_impression) AS impressions,
    SUM(ams_click) AS clicks,
    ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4) AS acos,
    ROUND((SUM(ams_sales) / NULLIF(SUM(ams_spend), 0))::numeric, 4) AS roas
FROM intermediate_amazon_ams_campaigns_belliwelli_view
WHERE report_date >= DATE '2026-07-01'
  AND report_date <  DATE '2026-08-01'
GROUP BY report_date, campaign_name
ORDER BY spend DESC;
```
