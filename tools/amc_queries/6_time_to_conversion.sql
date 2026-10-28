-- Window total by ad type and click-to-purchase bucket (1 = within 1 hour, 2 = 1-24 hours,
-- 3 = 1-3 days, 4 = 4-7 days, 5 = 8-14 days). Monthly grain falls under the privacy floor.
SELECT ad_product_type,
       CASE WHEN SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc) <= 3600 THEN 1
            WHEN SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc) <= 86400 THEN 2
            WHEN SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc) <= 86400 * 3 THEN 3
            WHEN SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc) <= 86400 * 7 THEN 4
            ELSE 5 END AS ttc_bucket,
       SUM(total_purchases) AS purchases,
       SUM(new_to_brand_purchases) AS ntb_purchases,
       SUM(total_product_sales) AS sales,
       COUNT(DISTINCT user_id) AS customers
FROM amazon_attributed_events_by_conversion_time
WHERE conversion_event_subtype = 'order' AND total_purchases > 0 AND clicks > 0
GROUP BY 1, 2
