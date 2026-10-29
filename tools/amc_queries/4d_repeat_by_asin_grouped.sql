-- 4c with ASINs under 100 customers grouped as zz_other. Use for catalogs with thousands of low-volume ASINs (Displate).
WITH ev AS (
  SELECT user_id, tracked_asin, event_dt_utc,
         SUM(conversions) AS events, SUM(total_product_sales) AS sales, SUM(total_units_sold) AS units
  FROM conversions
  WHERE user_id IS NOT NULL AND event_subtype = 'order'
  GROUP BY 1, 2, 3
),
um AS (
  SELECT user_id, DATE_TRUNC('month', event_dt_utc) AS month_start, SUM(events) AS orders
  FROM ev GROUP BY 1, 2
),
firstm AS (SELECT user_id, MIN(month_start) AS first_month FROM um GROUP BY 1),
seg AS (
  SELECT um.user_id, um.month_start,
         CASE WHEN f.first_month < um.month_start OR um.orders >= 2 THEN 'repeat' ELSE 'one_time' END AS segment
  FROM um JOIN firstm f ON um.user_id = f.user_id
),
oa AS (
  SELECT user_id, tracked_asin, DATE_TRUNC('month', event_dt_utc) AS month_start,
         SUM(events) AS orders, SUM(sales) AS sales, SUM(units) AS units
  FROM ev GROUP BY 1, 2, 3
),
ac AS (
  SELECT tracked_asin, COUNT(DISTINCT user_id) AS n FROM oa
  WHERE EXTRACT(YEAR FROM month_start) = 2026 GROUP BY 1
)
SELECT CASE WHEN ac.n >= 100 THEN oa.tracked_asin ELSE 'zz_other' END AS tracked_asin,
       COUNT(DISTINCT oa.user_id) AS customers, SUM(oa.orders) AS orders, SUM(oa.sales) AS sales, SUM(oa.units) AS units,
       COUNT(DISTINCT CASE WHEN g.segment = 'repeat' THEN oa.user_id END) AS repeat_customers,
       SUM(CASE WHEN g.segment = 'repeat' THEN oa.orders ELSE 0 END) AS repeat_orders,
       SUM(CASE WHEN g.segment = 'repeat' THEN oa.sales ELSE 0 END) AS repeat_sales,
       COUNT(DISTINCT CASE WHEN g.segment = 'one_time' THEN oa.user_id END) AS one_time_customers,
       SUM(CASE WHEN g.segment = 'one_time' THEN oa.orders ELSE 0 END) AS one_time_orders,
       SUM(CASE WHEN g.segment = 'one_time' THEN oa.sales ELSE 0 END) AS one_time_sales
FROM oa JOIN seg g ON oa.user_id = g.user_id AND oa.month_start = g.month_start
JOIN ac ON oa.tracked_asin = ac.tracked_asin
WHERE EXTRACT(YEAR FROM oa.month_start) = 2026
GROUP BY 1
