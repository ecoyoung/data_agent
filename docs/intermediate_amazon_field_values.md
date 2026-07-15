# intermediate_amazon_ Field Values Profile

Generated at: `2026-07-15T03:58:24Z`
Tables analyzed: `462`
Tables sampled for values: `19`

## Scope

- Structure coverage includes all selectable `intermediate_amazon_` objects.
- Value enumeration samples only low-cardinality categorical fields.
- ASIN, SKU, ids, names, search terms, targeting text, URLs and other high-cardinality business keys are excluded.

## Main Table Types

| Domain | Tables | Common columns | Majority columns | Variant columns shown |
| --- | ---: | ---: | ---: | ---: |
| `1p_orders` | 18 | 16 | 0 | 7 |
| `ads_audience_campaign` | 25 | 1 | 15 | 46 |
| `amazon_intermediate` | 5 | 4 | 16 | 18 |
| `ams_advertised_product` | 46 | 13 | 23 | 13 |
| `ams_campaigns` | 35 | 27 | 1 | 0 |
| `ams_placement` | 32 | 0 | 30 | 14 |
| `ams_search_terms` | 34 | 16 | 17 | 3 |
| `ams_targeting` | 29 | 38 | 0 | 0 |
| `business_report` | 34 | 24 | 1 | 0 |
| `dsp` | 160 | 14 | 6 | 65 |
| `inventory_days` | 1 | 26 | 0 | 0 |
| `orders` | 35 | 3 | 21 | 2 |
| `returns` | 8 | 17 | 1 | 0 |

## Global Common Fields

| Column | Tables | Domains |
| --- | ---: | --- |
| `brand` | 458 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `year` | 453 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `month` | 453 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `quarter` | 453 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `model` | 440 | `1p_orders`, `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting`, `business_report` |
| `report_date` | 427 | `1p_orders`, `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting`, `business_report` |
| `customer` | 361 | `ads_audience_campaign`, `ams_advertised_product`, `ams_placement`, `ams_search_terms`, `ams_targeting`, `business_report`, `dsp`, `returns` |
| `profile_name` | 352 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting`, `dsp` |
| `report_type` | 319 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_targeting`, `dsp`, `returns` |
| `ams_spend` | 202 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_impression` | 201 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_click` | 201 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_units` | 201 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_sales` | 201 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_ctr` | 198 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_roas` | 191 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `campaign_id` | 180 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `budget_currency_code` | 180 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_cvr` | 180 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_acos` | 180 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `product_name` | 173 | `1p_orders`, `ads_audience_campaign`, `ams_advertised_product`, `business_report`, `dsp`, `orders`, `returns` |
| `vcc` | 168 | `dsp`, `inventory_days`, `returns` |
| `ams_cpc` | 164 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_targeting` |
| `campaign_name` | 156 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_orders` | 151 | `ads_audience_campaign`, `ams_advertised_product`, `ams_campaigns`, `ams_placement`, `ams_targeting` |
| `country_code` | 148 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `business_report`, `orders`, `returns` |
| `ams_same_sku_sales` | 145 | `ads_audience_campaign`, `ams_advertised_product`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_same_sku_units` | 145 | `ads_audience_campaign`, `ams_advertised_product`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `asin` | 132 | `1p_orders`, `amazon_intermediate`, `ams_advertised_product`, `business_report`, `dsp`, `inventory_days`, `orders`, `returns` |
| `category` | 130 | `1p_orders`, `ams_advertised_product`, `business_report`, `orders` |
| `ams_dpv` | 130 | `ads_audience_campaign`, `ams_campaigns`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_same_sku_orders` | 129 | `ams_advertised_product`, `ams_placement`, `ams_search_terms`, `ams_targeting` |
| `ams_type` | 116 | `ads_audience_campaign`, `ams_advertised_product`, `ams_placement`, `ams_targeting` |
| `ad_group_name` | 98 | `ams_advertised_product`, `ams_search_terms`, `ams_targeting` |
| `customer_name` | 97 | `1p_orders`, `ads_audience_campaign`, `amazon_intermediate`, `ams_campaigns`, `inventory_days`, `orders` |
| `ams_other_sku_sales` | 89 | `ams_advertised_product`, `ams_search_terms`, `ams_targeting` |
| `ams_other_sku_units` | 89 | `ams_advertised_product`, `ams_search_terms`, `ams_targeting` |
| `country` | 75 | `ads_audience_campaign`, `ams_campaigns`, `ams_search_terms` |
| `ad_type` | 73 | `amazon_intermediate`, `ams_campaigns`, `ams_search_terms` |
| `campaign_type` | 45 | `ads_audience_campaign`, `amazon_intermediate`, `ams_campaigns` |
| `campaign_tag` | 45 | `ads_audience_campaign`, `amazon_intermediate`, `ams_campaigns` |
| `sku` | 44 | `amazon_intermediate`, `inventory_days`, `orders`, `returns` |
| `time` | 24 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product`, `ams_search_terms` |
| `ams_order` | 17 | `ads_audience_campaign`, `amazon_intermediate`, `ams_advertised_product` |
| `date` | 3 | `amazon_intermediate`, `ams_placement`, `dsp` |

## Common Fields By Domain

### `1p_orders`

- Common: `asin`, `brand`, `category`, `country_code`, `customer_name`, `glance_view`, `local_currency`, `model`, `month`, `product_name`, `quarter`, `report_date`, `shipped_cogs`, `shipped_revenue`, `shipped_units`, `year`
- Majority: -

### `ads_audience_campaign`

- Common: `brand`
- Majority: `ams_click`(88%), `ams_cpc`(88%), `ams_ctr`(88%), `ams_impression`(88%), `ams_roas`(88%), `ams_sales`(88%), `ams_spend`(88%), `ams_units`(88%), `campaign_name`(88%), `month`(88%), `profile_name`(88%), `quarter`(88%), `year`(88%), `customer`(76%), `model`(76%)

### `amazon_intermediate`

- Common: `ams_order`, `ams_spend`, `country_code`, `p_type`
- Majority: `ad_type`(80%), `ams_click`(80%), `ams_impression`(80%), `ams_sales`(80%), `ams_units`(80%), `bussines_units`(80%), `campaign_name`(80%), `campaign_tag`(80%), `campaign_type`(80%), `country_code_request`(80%), `dpv14d`(80%), `roas14d`(80%), `subcategory`(80%), `time`(80%), `time_window_start`(80%), `vcp_category`(80%)

### `ams_advertised_product`

- Common: `ams_click`, `ams_cpc`, `ams_ctr`, `ams_impression`, `ams_sales`, `ams_spend`, `ams_units`, `brand`, `country_code`, `customer`, `model`, `product_name`, `profile_name`
- Majority: `category`(97%), `month`(97%), `quarter`(97%), `year`(97%), `ad_group_name`(86%), `advertised_asin`(86%), `advertised_sku`(86%), `ams_acos`(86%), `ams_cvr`(86%), `ams_ntb_orders`(86%), `ams_ntb_sales`(86%), `ams_ntb_units`(86%), `ams_orders`(86%), `ams_roas`(86%), `ams_same_sku_orders`(86%), `ams_same_sku_sales`(86%)

### `ams_campaigns`

- Common: `ad_type`, `ams_acos`, `ams_click`, `ams_cpc`, `ams_ctr`, `ams_cvr`, `ams_dpv`, `ams_impression`, `ams_orders`, `ams_roas`, `ams_sales`, `ams_spend`, `ams_units`, `brand`, `budget_currency_code`, `campaign_id`, `campaign_name`, `campaign_tag`, `campaign_type`, `country`, `customer_name`, `month`, `profile_name`, `quarter`
- Majority: `model`(88%)

### `ams_placement`

- Common: -
- Majority: `ams_acos`(96%), `ams_click`(96%), `ams_cpc`(96%), `ams_ctr`(96%), `ams_cvr`(96%), `ams_dpv`(96%), `ams_impression`(96%), `ams_orders`(96%), `ams_roas`(96%), `ams_sales`(96%), `ams_same_sku_orders`(96%), `ams_same_sku_sales`(96%), `ams_same_sku_units`(96%), `ams_spend`(96%), `ams_top_of_search_impression_share`(96%), `ams_type`(96%)

### `ams_search_terms`

- Common: `ad_order`, `ad_type`, `ams_click`, `ams_ctr`, `ams_impression`, `ams_roas`, `ams_sales`, `ams_spend`, `ams_units`, `brand`, `country`, `customer`, `month`, `quarter`, `search_term`, `year`
- Majority: `ad_group_name`(85%), `ams_acos`(85%), `ams_cvr`(85%), `ams_dpv`(85%), `ams_other_sku_orders`(85%), `ams_other_sku_sales`(85%), `ams_other_sku_units`(85%), `ams_same_sku_orders`(85%), `ams_same_sku_sales`(85%), `ams_same_sku_units`(85%), `budget_currency_code`(85%), `campaign_id`(85%), `campaign_name`(85%), `model`(85%), `profile_name`(85%), `report_date`(85%)

### `ams_targeting`

- Common: `ad_group_name`, `ams_acos`, `ams_atc`, `ams_click`, `ams_cpc`, `ams_ctr`, `ams_cvr`, `ams_dpv`, `ams_impression`, `ams_ntb_order`, `ams_ntb_sales`, `ams_ntb_units`, `ams_orders`, `ams_other_sku_sales`, `ams_other_sku_units`, `ams_roas`, `ams_sales`, `ams_same_sku_orders`, `ams_same_sku_sales`, `ams_same_sku_units`, `ams_spend`, `ams_tos_impression_share`, `ams_type`, `ams_units`
- Majority: -

### `business_report`

- Common: `asin`, `brand`, `country_code`, `customer`, `model`, `month`, `product_name`, `quarter`, `report_date`, `salesbyasin_orderedproductsales_amount`, `salesbyasin_orderedproductsales_currencycode`, `salesbyasin_totalorderitems`, `salesbyasin_unitsordered`, `salesbyasin_unitsorderedb2b`, `trafficbyasin_browserpageviews`, `trafficbyasin_browsersessionpercentage`, `trafficbyasin_browsersessions`, `trafficbyasin_buyboxpercentage`, `trafficbyasin_mobileapppageviews`, `trafficbyasin_mobileappsessions`, `trafficbyasin_pageviews`, `trafficbyasin_sessions`, `trafficbyasin_unitsessionpercentage`, `year`
- Majority: `category`(97%)

### `dsp`

- Common: `ads_type`, `brand`, `currency_code`, `customer`, `dsp_ntb_purchases`, `dsp_purchases`, `model`, `month`, `profile_name`, `quarter`, `report_date`, `report_type`, `vcc`, `year`
- Majority: `advertiser_name`(85%), `order_name`(84%), `dsp_click`(81%), `dsp_cost`(81%), `dsp_dpv`(81%), `dsp_impression`(81%)

### `inventory_days`

- Common: `all_available_inventory_days`, `asin`, `available_inventory_days`, `available_quantity`, `avg_30d_units`, `brand`, `customer_name`, `inbound_quantity`, `inbound_received_quantity`, `inbound_shipped_quantity`, `inbound_working_quantity`, `inv_age_0_to_30_days`, `inv_age_0_to_90_days`, `inv_age_181_to_270_days`, `inv_age_181_to_330_days`, `inv_age_271_to_365_days`, `inv_age_31_to_60_days`, `inv_age_331_to_365_days`, `inv_age_366_to_455_days`, `inv_age_456_plus_days`, `inv_age_61_to_90_days`, `inv_age_91_to_180_days`, `model`, `report_date`
- Majority: -

### `orders`

- Common: `order_items`, `ordered_revenue`, `ordered_units`
- Majority: `asin`(97%), `brand`(97%), `category`(97%), `country_code`(97%), `customer_name`(97%), `fulfillment_channel`(97%), `item_tax`(97%), `local_currency`(97%), `model`(97%), `month`(97%), `order_status`(97%), `product_name`(97%), `product_priority`(97%), `quarter`(97%), `report_date`(97%), `sales_channel`(97%)

### `returns`

- Common: `asin`, `brand`, `country_code`, `customer`, `customer_comments`, `model`, `month`, `order_id`, `product_name`, `quarter`, `reason`, `report_type`, `return_date`, `return_units`, `sku`, `status`, `year`
- Majority: `vcc`(87%)

## Scope-Specific / Variant Fields

These are fields that appear in only a small minority of tables within the same domain. They are candidates for brand/store-specific handling, not necessarily guaranteed unique business semantics.

| Domain | Scope | Fields |
| --- | --- | --- |
| `ads_audience_campaign` | `vitalproteinsbv` | `rn` |
| `amazon_intermediate` | `ams_time` | `date`, `time_of_day` |
| `amazon_intermediate` | `philips` | `ams_cpc`, `ams_ctr`, `ams_same_sales`, `asin`, `date_time`, `id`, `sku`, `subcategory_lev2` |
| `amazon_intermediate` | `philips_view_2` | `ams_same_sales` |
| `ams_placement` | `philips_dashboard_m` | `adType`, `campaignName`, `click`, `date`, `impression`, `order`, `placement`, `row_id`, `sales`, `site`, `spend`, `subcategory`, `trafficType`, `vcp` |
| `dsp` | `bestqi` | `date` |
| `inventory_days` | `blueland` | `all_available_inventory_days`, `asin`, `available_inventory_days`, `available_quantity`, `avg_30d_units`, `brand`, `customer_name`, `inbound_quantity`, `inbound_received_quantity`, `inbound_shipped_quantity`, `inbound_working_quantity`, `inv_age_0_to_30_days`, `inv_age_0_to_90_days`, `inv_age_181_to_270_days`, `inv_age_181_to_330_days`, `inv_age_271_to_365_days`, `inv_age_31_to_60_days`, `inv_age_331_to_365_days`, `inv_age_366_to_455_days`, `inv_age_456_plus_days` |
| `orders` | `vp_us_weekly_state` | `state`, `week_key` |

## Enumerated Field Values

| Domain | Scope | Table | Column | Status | Values from sample |
| --- | --- | --- | --- | --- | --- |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `ads_type` | `ok` | SP (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `brand` | `ok` | BrüMate (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `campaign_type` | `ok` | Sponsored product (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `country` | `ok` | US (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `customer_name` | `ok` | BrüMate (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_ad_campaign_brumate_view` | `p_type` | `ok` | 3P (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_dsp_campaign_ad_brumate_view` | `brand` | `ok` | BrüMate-US-US (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_dsp_campaign_ad_brumate_view` | `country_code` | `ok` | US (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_dsp_campaign_ad_brumate_view` | `customer` | `ok` | BrüMate (2000) |
| `ads_audience_campaign` | `brumate` | `intermediate_amazon_ads_dsp_campaign_ad_brumate_view` | `model` | `ok` | 3P (2000) |
| `ams_advertised_product` | `innerbrightness` | `intermediate_amazon_ams_advertised_product_innerbrightness_view` | `ams_type` | `ok` | SP (2000) |
| `ams_advertised_product` | `innerbrightness` | `intermediate_amazon_ams_advertised_product_innerbrightness_view` | `country_code` | `ok` | US (2000) |
| `ams_advertised_product` | `innerbrightness` | `intermediate_amazon_ams_advertised_product_innerbrightness_view` | `customer` | `ok` | Inner brightness-New (2000) |
| `ams_advertised_product` | `innerbrightness` | `intermediate_amazon_ams_advertised_product_innerbrightness_view` | `model` | `ok` | 3P (2000) |
| `ams_advertised_product` | `innerbrightness` | `intermediate_amazon_ams_advertised_product_innerbrightness_view` | `report_type` | `ok` | spAdvertisedProduct (2000) |
| `ams_advertised_product` | `brumate` | `intermediate_amazon_ads_sp_sd_advertised_brumate_view` | `brand` | `ok` | BrüMate (2000) |
| `ams_advertised_product` | `brumate` | `intermediate_amazon_ads_sp_sd_advertised_brumate_view` | `country_code` | `ok` | US (2000) |
| `ams_advertised_product` | `brumate` | `intermediate_amazon_ads_sp_sd_advertised_brumate_view` | `customer` | `ok` | BrüMate (2000) |
| `ams_advertised_product` | `brumate` | `intermediate_amazon_ads_sp_sd_advertised_brumate_view` | `model` | `ok` | 3P (2000) |
| `ams_advertised_product` | `brumate` | `intermediate_amazon_ads_sp_sd_advertised_brumate_view` | `category` | `ok` | Kitchen & Dining (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `ad_type` | `ok` | SP (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `brand` | `ok` | Inner brightness (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `campaign_type` | `ok` | Sponsored product (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `country` | `ok` | US (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `customer_name` | `ok` | Inner brightness-New (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `model` | `ok` | 3P (2000) |
| `ams_campaigns` | `innerbrightness` | `intermediate_amazon_ams_campaigns_innerbrightness_view` | `report_type` | `ok` | spCampaigns (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `ad_type` | `ok` | SP (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `brand` | `ok` | BrüMate (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `campaign_type` | `ok` | Sponsored product (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `country` | `ok` | US (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `customer_name` | `ok` | BrüMate-US-US (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `model` | `ok` | 3P (2000) |
| `ams_campaigns` | `brumate` | `intermediate_amazon_ams_campaigns_brumate_view` | `report_type` | `ok` | spCampaigns (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `ams_type` | `ok` | SP (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `brand` | `ok` | BrüMate (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `customer` | `ok` | BrüMate-US-US (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `model` | `ok` | 3P (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `report_type` | `ok` | spCampaign_placement (2000) |
| `ams_placement` | `brumate` | `intermediate_amazon_ams_campaigns_placement_brumate_view` | `placement_classification` | `ok` | Other on-Amazon (613); Detail Page on-Amazon (591); Top of Search on-Amazon (543); Off Amazon (253) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `ams_type` | `ok` | SP (2000) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `brand` | `ok` | Blueland (2000) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `customer` | `ok` | Blueland_US-US-US-US (2000) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `model` | `ok` | 3P (2000) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `report_type` | `ok` | spCampaign_placement (2000) |
| `ams_placement` | `blueland` | `intermediate_amazon_ams_campaigns_placement_blueland_view` | `placement_classification` | `ok` | Other on-Amazon (680); Detail Page on-Amazon (663); Top of Search on-Amazon (564); Off Amazon (93) |
| `ams_search_terms` | `innerbrightness` | `intermediate_amazon_ams_search_term_innerbrightness_view` | `ad_type` | `ok` | SP (2000) |
| `ams_search_terms` | `innerbrightness` | `intermediate_amazon_ams_search_term_innerbrightness_view` | `brand` | `ok` | Inner brightness (2000) |
| `ams_search_terms` | `innerbrightness` | `intermediate_amazon_ams_search_term_innerbrightness_view` | `country` | `ok` | US (2000) |
| `ams_search_terms` | `innerbrightness` | `intermediate_amazon_ams_search_term_innerbrightness_view` | `customer` | `ok` | Inner brightness-New (2000) |
| `ams_search_terms` | `innerbrightness` | `intermediate_amazon_ams_search_term_innerbrightness_view` | `model` | `ok` | 3P (2000) |
| `ams_targeting` | `innerbrightness` | `intermediate_amazon_ams_targeting_innerbrightness_view` | `ams_type` | `ok` | SP (2000) |
| `ams_targeting` | `innerbrightness` | `intermediate_amazon_ams_targeting_innerbrightness_view` | `brand` | `ok` | Inner brightness (2000) |
| `ams_targeting` | `innerbrightness` | `intermediate_amazon_ams_targeting_innerbrightness_view` | `customer` | `ok` | Inner brightness-New (2000) |
| `ams_targeting` | `innerbrightness` | `intermediate_amazon_ams_targeting_innerbrightness_view` | `model` | `ok` | 3P (2000) |
| `ams_targeting` | `innerbrightness` | `intermediate_amazon_ams_targeting_innerbrightness_view` | `report_type` | `ok` | spTargeting (2000) |
| `business_report` | `innerbrightness` | `intermediate_amazon_3p_sales_and_traffic_innerbrightness_view` | `brand` | `ok` | Inner brightness-New (2000) |
| `business_report` | `innerbrightness` | `intermediate_amazon_3p_sales_and_traffic_innerbrightness_view` | `country_code` | `ok` | US (2000) |
| `business_report` | `innerbrightness` | `intermediate_amazon_3p_sales_and_traffic_innerbrightness_view` | `customer` | `ok` | Inner brightness-New (2000) |
| `business_report` | `innerbrightness` | `intermediate_amazon_3p_sales_and_traffic_innerbrightness_view` | `model` | `ok` | 3P (2000) |
| `business_report` | `brumate` | `intermediate_amazon_3p_sales_and_traffic_brumate_view` | `brand` | `ok` | BrüMate (2000) |
| `business_report` | `brumate` | `intermediate_amazon_3p_sales_and_traffic_brumate_view` | `country_code` | `ok` | US (2000) |
| `business_report` | `brumate` | `intermediate_amazon_3p_sales_and_traffic_brumate_view` | `customer` | `ok` | BrüMate-US-US (2000) |
| `business_report` | `brumate` | `intermediate_amazon_3p_sales_and_traffic_brumate_view` | `model` | `ok` | 3P (2000) |
| `business_report` | `brumate` | `intermediate_amazon_3p_sales_and_traffic_brumate_view` | `category` | `ok` | Kitchen & Dining (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `brand` | `ok` | Blueland (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `country_code` | `ok` | US (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `customer` | `ok` | Blueland_US-US-US-US (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `model` | `ok` | 3p (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `reason` | `ok` | ORDERED_WRONG_ITEM (366); DEFECTIVE (297); UNWANTED_ITEM (272); UNDELIVERABLE_UNKNOWN (261); FOUND_BETTER_PRICE (174); NOT_AS_DESCRIBED (150); DAMAGED_BY_FC (106); SWITCHEROO (86) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `report_type` | `ok` | return (2000) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `status` | `ok` | Unit returned to inventory (1143); IMMEDIATE_DISPOSAL (415); IMMEDIATE_DONATION (409); Reimbursed (33) |
| `returns` | `blueland` | `intermediate_amazon_fba_returns_blueland_view` | `vcc` | `ok` | VCC-家居生活_Blueland (2000) |

## Enumeration Summary

### Status

| Status | Count |
| --- | ---: |
| `ok` | 73 |
| `timeout` | 36 |
| `no_values` | 5 |

### Most Enumerated Columns

| Column | Attempts |
| --- | ---: |
| `brand` | 19 |
| `model` | 18 |
| `customer` | 13 |
| `country_code` | 9 |
| `report_type` | 9 |
| `customer_name` | 6 |
| `category` | 6 |
| `country` | 5 |
| `ams_type` | 5 |
| `ad_type` | 4 |
| `campaign_type` | 3 |
| `vcc` | 3 |
| `placement_classification` | 2 |
| `fulfillment_channel` | 2 |
| `order_status` | 2 |
| `sales_channel` | 2 |
| `reason` | 2 |
| `status` | 2 |
| `ads_type` | 1 |
| `p_type` | 1 |
