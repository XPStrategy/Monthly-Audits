WITH ev AS (
  SELECT user_id, event_dt_utc, event_subtype,
         SUM(conversions) AS events, SUM(total_product_sales) AS sales, SUM(total_units_sold) AS units
  FROM conversions
  WHERE user_id IS NOT NULL AND event_subtype IN ('order', 'snsSubscription')
  GROUP BY 1, 2, 3
),
subs AS (SELECT user_id, MIN(DATE_TRUNC('month', event_dt_utc)) AS sns_month FROM ev WHERE event_subtype = 'snsSubscription' GROUP BY 1),
um AS (
  SELECT user_id, DATE_TRUNC('month', event_dt_utc) AS month_start,
         SUM(events) AS orders, SUM(sales) AS sales, SUM(units) AS units
  FROM ev WHERE event_subtype = 'order' GROUP BY 1, 2
),
firstm AS (SELECT user_id, MIN(month_start) AS first_month FROM um GROUP BY 1),
seg AS (
  SELECT um.user_id, um.month_start, um.orders, um.sales, um.units,
         CASE WHEN s.sns_month IS NOT NULL AND s.sns_month <= um.month_start THEN 'sns'
              WHEN f.first_month < um.month_start OR um.orders >= 2 THEN 'repeat'
              ELSE 'one_time' END AS segment
  FROM um JOIN firstm f ON um.user_id = f.user_id LEFT JOIN subs s ON um.user_id = s.user_id
),
agg AS (
  SELECT month_start,
         COUNT(DISTINCT user_id) AS customers, SUM(orders) AS orders, SUM(sales) AS sales, SUM(units) AS units,
         COUNT(DISTINCT CASE WHEN segment = 'sns' THEN user_id END) AS sns_customers,
         SUM(CASE WHEN segment = 'sns' THEN orders ELSE 0 END) AS sns_orders,
         SUM(CASE WHEN segment = 'sns' THEN sales ELSE 0 END) AS sns_sales,
         COUNT(DISTINCT CASE WHEN segment = 'repeat' THEN user_id END) AS repeat_customers,
         SUM(CASE WHEN segment = 'repeat' THEN orders ELSE 0 END) AS repeat_orders,
         SUM(CASE WHEN segment = 'repeat' THEN sales ELSE 0 END) AS repeat_sales,
         COUNT(DISTINCT CASE WHEN segment = 'one_time' THEN user_id END) AS one_time_customers,
         SUM(CASE WHEN segment = 'one_time' THEN orders ELSE 0 END) AS one_time_orders,
         SUM(CASE WHEN segment = 'one_time' THEN sales ELSE 0 END) AS one_time_sales
  FROM seg GROUP BY 1
),
sg AS (SELECT DATE_TRUNC('month', event_dt_utc) AS month_start, COUNT(DISTINCT user_id) AS sns_signups FROM ev WHERE event_subtype = 'snsSubscription' GROUP BY 1)
SELECT a.*, g.sns_signups FROM agg a LEFT JOIN sg g ON a.month_start = g.month_start
