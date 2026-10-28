WITH ord AS (
  SELECT user_id, DATE_TRUNC('month', event_dt_utc) AS month_start,
         MIN(event_dt_utc) AS first_order_dt, SUM(conversions) AS orders, SUM(total_product_sales) AS sales
  FROM conversions
  WHERE event_subtype = 'order' AND user_id IS NOT NULL
  GROUP BY 1, 2
),
tch AS (
  SELECT user_id, ad_product_type, DATE_TRUNC('day', event_dt_utc) AS touch_day,
         MIN(event_dt_utc) AS t_min, SUM(clicks) AS clicks
  FROM sponsored_ads_traffic
  WHERE user_id IS NOT NULL AND ad_product_type IS NOT NULL
  GROUP BY 1, 2, 3
),
j AS (
  SELECT o.user_id, o.month_start, o.first_order_dt, o.orders, o.sales,
         t.ad_product_type, t.touch_day, t.t_min, t.clicks
  FROM ord o
  JOIN tch t
    ON o.user_id = t.user_id
   AND t.t_min <= o.first_order_dt
   AND SECONDS_BETWEEN(t.t_min, o.first_order_dt) <= 2592000
),
ut AS (SELECT DISTINCT user_id, month_start, ad_product_type FROM j),
pp AS (
  SELECT user_id, month_start, ARRAY_JOIN(ARRAY_SORT(COLLECT(ad_product_type)), ' + ') AS path
  FROM ut GROUP BY 1, 2
),
ps AS (
  SELECT user_id, month_start, MAX(orders) AS orders, MAX(sales) AS sales,
         COUNT(DISTINCT touch_day) AS touch_days, SUM(clicks) AS clicks,
         MIN(t_min) AS first_touch, MAX(first_order_dt) AS first_order_dt
  FROM j GROUP BY 1, 2
)
SELECT ps.month_start, pp.path,
       COUNT(DISTINCT ps.user_id) AS buyers, SUM(ps.orders) AS orders, SUM(ps.sales) AS sales,
       AVG(ps.touch_days) AS avg_touch_days,
       AVG(SECONDS_BETWEEN(ps.first_touch, ps.first_order_dt) / 86400.0) AS avg_days_first_touch_to_order,
       COUNT(DISTINCT CASE WHEN ps.clicks > 0 THEN ps.user_id END) AS buyers_who_clicked
FROM ps
JOIN pp ON ps.user_id = pp.user_id AND ps.month_start = pp.month_start
WHERE EXTRACT(YEAR FROM ps.month_start) = 2026
GROUP BY 1, 2
