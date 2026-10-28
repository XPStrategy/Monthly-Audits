-- Fixed-lookback variant (draft, not yet run): repeat = ordered in any of the 3 prior calendar months
-- or 2+ orders this month, so every reporting month uses the same history window. Run from 3 months
-- before the reporting window; keep only reporting months.
WITH ev AS (
  SELECT user_id, tracked_asin, event_dt_utc, event_subtype,
         SUM(conversions) AS events, SUM(total_product_sales) AS sales, SUM(total_units_sold) AS units
  FROM conversions
  WHERE user_id IS NOT NULL AND event_subtype IN ('order', 'snsSubscription')
  GROUP BY 1, 2, 3, 4
),
subs AS (
  SELECT user_id, MIN(DATE_TRUNC('month', event_dt_utc)) AS sns_month
  FROM ev WHERE event_subtype = 'snsSubscription' GROUP BY 1
),
um AS (
  SELECT user_id, DATE_TRUNC('month', event_dt_utc) AS month_start, SUM(events) AS orders
  FROM ev WHERE event_subtype = 'order' GROUP BY 1, 2
),
prior AS (
  -- user ordered in at least one of the 3 calendar months before this month (same window for every month)
  SELECT DISTINCT a.user_id, a.month_start
  FROM um a JOIN um b ON a.user_id = b.user_id
   AND b.month_start < a.month_start AND SECONDS_BETWEEN(b.month_start, a.month_start) <= 7948800
),
firstm AS (
  SELECT user_id, MIN(month_start) AS first_month FROM um GROUP BY 1
),
seg AS (
  SELECT um.user_id, um.month_start,
         CASE WHEN s.sns_month IS NOT NULL AND s.sns_month <= um.month_start THEN 'sns'
              WHEN p.user_id IS NOT NULL OR um.orders >= 2 THEN 'repeat'
              ELSE 'one_time' END AS segment
  FROM um
  JOIN firstm f ON um.user_id = f.user_id
  LEFT JOIN subs s ON um.user_id = s.user_id
  LEFT JOIN prior p ON um.user_id = p.user_id AND um.month_start = p.month_start
),
oa AS (
  SELECT user_id, tracked_asin, DATE_TRUNC('month', event_dt_utc) AS month_start,
         SUM(events) AS orders, SUM(sales) AS sales, SUM(units) AS units
  FROM ev WHERE event_subtype = 'order' GROUP BY 1, 2, 3
),
agg AS (
  SELECT oa.tracked_asin,
         COUNT(DISTINCT oa.user_id) AS customers, SUM(oa.orders) AS orders, SUM(oa.sales) AS sales, SUM(oa.units) AS units,
         COUNT(DISTINCT CASE WHEN g.segment = 'sns' THEN oa.user_id END) AS sns_customers,
         SUM(CASE WHEN g.segment = 'sns' THEN oa.orders ELSE 0 END) AS sns_orders,
         SUM(CASE WHEN g.segment = 'sns' THEN oa.sales ELSE 0 END) AS sns_sales,
         COUNT(DISTINCT CASE WHEN g.segment = 'repeat' THEN oa.user_id END) AS repeat_customers,
         SUM(CASE WHEN g.segment = 'repeat' THEN oa.orders ELSE 0 END) AS repeat_orders,
         SUM(CASE WHEN g.segment = 'repeat' THEN oa.sales ELSE 0 END) AS repeat_sales,
         COUNT(DISTINCT CASE WHEN g.segment = 'one_time' THEN oa.user_id END) AS one_time_customers,
         SUM(CASE WHEN g.segment = 'one_time' THEN oa.orders ELSE 0 END) AS one_time_orders,
         SUM(CASE WHEN g.segment = 'one_time' THEN oa.sales ELSE 0 END) AS one_time_sales
  FROM oa
  JOIN seg g ON oa.user_id = g.user_id AND oa.month_start = g.month_start
  WHERE EXTRACT(YEAR FROM oa.month_start) = 2026
  GROUP BY 1
),
sga AS (
  SELECT tracked_asin, COUNT(DISTINCT user_id) AS sns_signups_2026
  FROM ev
  WHERE event_subtype = 'snsSubscription' AND EXTRACT(YEAR FROM event_dt_utc) = 2026
  GROUP BY 1
)
SELECT a.*, s.sns_signups_2026
FROM agg a LEFT JOIN sga s ON a.tracked_asin = s.tracked_asin
