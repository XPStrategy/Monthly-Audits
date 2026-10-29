-- Repeat vs one-time by month without the SnS split. Use when SnS is absent or tiny: a monthly SnS sign-up count under ~100 blanks that month in 3_repeat_sns_monthly.sql. Run from 3 months before the window.
WITH ev AS (
  SELECT user_id, event_dt_utc,
         SUM(conversions) AS events, SUM(total_product_sales) AS sales, SUM(total_units_sold) AS units
  FROM conversions
  WHERE user_id IS NOT NULL AND event_subtype = 'order'
  GROUP BY 1, 2
),
um AS (
  SELECT user_id, DATE_TRUNC('month', event_dt_utc) AS month_start,
         SUM(events) AS orders, SUM(sales) AS sales, SUM(units) AS units
  FROM ev GROUP BY 1, 2
),
firstm AS (SELECT user_id, MIN(month_start) AS first_month FROM um GROUP BY 1),
seg AS (
  SELECT um.user_id, um.month_start, um.orders, um.sales,
         CASE WHEN f.first_month < um.month_start OR um.orders >= 2 THEN 'repeat' ELSE 'one_time' END AS segment
  FROM um JOIN firstm f ON um.user_id = f.user_id
)
SELECT month_start,
       COUNT(DISTINCT user_id) AS customers, SUM(orders) AS orders, SUM(sales) AS sales,
       COUNT(DISTINCT CASE WHEN segment = 'repeat' THEN user_id END) AS repeat_customers,
       SUM(CASE WHEN segment = 'repeat' THEN orders ELSE 0 END) AS repeat_orders,
       SUM(CASE WHEN segment = 'repeat' THEN sales ELSE 0 END) AS repeat_sales,
       COUNT(DISTINCT CASE WHEN segment = 'one_time' THEN user_id END) AS one_time_customers,
       SUM(CASE WHEN segment = 'one_time' THEN orders ELSE 0 END) AS one_time_orders,
       SUM(CASE WHEN segment = 'one_time' THEN sales ELSE 0 END) AS one_time_sales
FROM seg GROUP BY 1
