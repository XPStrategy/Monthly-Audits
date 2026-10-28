WITH u AS (
  SELECT DATE_TRUNC('month', conversion_event_dt) AS month_start,
         ad_product_type AS product_type, user_id,
         SUM(total_purchases) AS purchases, SUM(new_to_brand_purchases) AS ntb_purchases,
         SUM(total_product_sales) AS sales, SUM(new_to_brand_product_sales) AS ntb_sales,
         SUM(total_units_sold) AS units
  FROM amazon_attributed_events_by_conversion_time
  WHERE total_purchases > 0 AND user_id IS NOT NULL
  GROUP BY 1, 2, 3
),
ua AS (
  SELECT month_start, user_id, SUM(purchases) AS purchases, SUM(ntb_purchases) AS ntb_purchases,
         SUM(sales) AS sales, SUM(ntb_sales) AS ntb_sales, SUM(units) AS units
  FROM u GROUP BY 1, 2
),
sp AS (
  SELECT DATE_TRUNC('month', event_dt) AS month_start, ad_product_type AS product_type,
         SUM(spend) / 100000000.0 AS spend, SUM(clicks) AS clicks
  FROM sponsored_ads_traffic GROUP BY 1, 2
),
spa AS (SELECT month_start, SUM(spend) AS spend, SUM(clicks) AS clicks FROM sp GROUP BY 1),
pt AS (
  SELECT month_start, product_type, COUNT(DISTINCT user_id) AS customers,
         COUNT(DISTINCT CASE WHEN ntb_purchases > 0 THEN user_id END) AS ntb_customers,
         SUM(purchases) AS purchases, SUM(ntb_purchases) AS ntb_purchases,
         SUM(sales) AS sales, SUM(ntb_sales) AS ntb_sales, SUM(units) AS units
  FROM u GROUP BY 1, 2
),
acct AS (
  SELECT month_start, COUNT(DISTINCT user_id) AS customers,
         COUNT(DISTINCT CASE WHEN ntb_purchases > 0 THEN user_id END) AS ntb_customers,
         SUM(purchases) AS purchases, SUM(ntb_purchases) AS ntb_purchases,
         SUM(sales) AS sales, SUM(ntb_sales) AS ntb_sales, SUM(units) AS units
  FROM ua GROUP BY 1
)
SELECT 'account' AS view_level, a.month_start, 'all' AS product_type, a.customers, a.ntb_customers,
       a.purchases, a.ntb_purchases, a.sales, a.ntb_sales, a.units, s.spend, s.clicks
FROM acct a LEFT JOIN spa s ON a.month_start = s.month_start
UNION ALL
SELECT 'product_type', p.month_start, p.product_type, p.customers, p.ntb_customers,
       p.purchases, p.ntb_purchases, p.sales, p.ntb_sales, p.units, s.spend, s.clicks
FROM pt p LEFT JOIN sp s ON p.month_start = s.month_start AND p.product_type = s.product_type
