-- Rollback for add_recommended_indexes.sql.
-- Drops every index created by that script, idempotently.

DROP INDEX CONCURRENTLY IF EXISTS idx_3p_orders_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_3p_orders_asin;
DROP INDEX CONCURRENTLY IF EXISTS idx_br_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_br_childasin;
DROP INDEX CONCURRENTLY IF EXISTS idx_shipments_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_shipments_asin;
DROP INDEX CONCURRENTLY IF EXISTS idx_returns_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_returns_asin;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_snapshot_date_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_snapshot_sku;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_health_snapshot_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_health_sku;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_planning_snapshot_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_inventory_planning_sku;
DROP INDEX CONCURRENTLY IF EXISTS idx_replenishment_report_month_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_replenishment_asin;

DROP INDEX CONCURRENTLY IF EXISTS idx_sp_camp_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_camp_campaign_id;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_st_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_st_search_term;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_targeting_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_targeting_keyword;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_adv_prod_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_adv_prod_asin;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_placement_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_purchased_prod_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sp_purchased_prod_asin;

DROP INDEX CONCURRENTLY IF EXISTS idx_sb_camp_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_camp_campaign_id;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_st_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_st_search_term;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_targeting_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_targeting_keyword;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_placement_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_purchased_prod_date_country_customer;
DROP INDEX CONCURRENTLY IF EXISTS idx_sb_purchased_prod_asin;
