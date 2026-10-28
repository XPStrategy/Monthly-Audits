WITH ntb AS (
  SELECT user_id, campaign_id, conversion_event_dt_utc AS conv_dt,
         SUM(new_to_brand_purchases) AS ntb_purchases, SUM(new_to_brand_product_sales) AS ntb_sales
  FROM amazon_attributed_events_by_conversion_time
  WHERE new_to_brand_purchases > 0 AND user_id IS NOT NULL
  GROUP BY 1, 2, 3
),
clk AS (
  SELECT DISTINCT user_id, campaign_id, ad_product_type, customer_search_term, event_dt_utc AS click_dt
  FROM sponsored_ads_traffic
  WHERE clicks > 0 AND customer_search_term IS NOT NULL AND user_id IS NOT NULL
),
m AS (
  SELECT DISTINCT c.customer_search_term, c.ad_product_type, n.user_id, n.conv_dt, n.ntb_purchases, n.ntb_sales
  FROM ntb n
  JOIN clk c ON n.user_id = c.user_id AND n.campaign_id = c.campaign_id
   AND c.click_dt <= n.conv_dt AND SECONDS_BETWEEN(c.click_dt, n.conv_dt) <= 1209600
),
agg AS (
  SELECT customer_search_term, ad_product_type, COUNT(DISTINCT user_id) AS ntb_customers,
         SUM(ntb_purchases) AS ntb_purchases, SUM(ntb_sales) AS ntb_sales
  FROM m GROUP BY 1, 2
),
sp AS (
  SELECT customer_search_term, ad_product_type, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
         SUM(spend) / 100000000.0 AS spend
  FROM sponsored_ads_traffic WHERE customer_search_term IS NOT NULL GROUP BY 1, 2
)
SELECT a.customer_search_term, a.ad_product_type, a.ntb_customers, a.ntb_purchases, a.ntb_sales,
       s.impressions, s.clicks, s.spend
FROM agg a
LEFT JOIN sp s ON a.customer_search_term = s.customer_search_term AND a.ad_product_type = s.ad_product_type
