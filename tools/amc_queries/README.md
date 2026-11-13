# AMC query pack (Marketplace Ad Pros `run_amc_query`)

Six queries, one per AMC Insights tab. Sponsored Ads tables only. The date range is set in the run call, not the SQL.

| File | Window (run call) | Tab |
|---|---|---|
| 1_ntb_monthly.sql | review window | New-to-Brand |
| 2_ntb_search_terms.sql | review window | NTB Search Terms |
| 3_repeat_sns_monthly.sql | review window, start 3 months earlier (lookback) | Repeat & SnS |
| 4_repeat_sns_by_asin.sql | same as 3 | Repeat & SnS (by ASIN) |
| 5_path_to_conversion.sql | review window, start 1 month earlier (30-day lookback) | Path to Conversion |
| 6_time_to_conversion.sql | review window | Time to Conversion |

Queries 3, 4 and 5 keep only the review year with `EXTRACT(YEAR FROM ...)`; change the year when the window crosses into a new year.
Limits: 2 queries in flight per MAP account, 25 per day. Run after the 15th so the prior month has its full 14-day attribution.
Saving results: `tools/amc_from_transcript.py <session.jsonl> <query_id> <folder>/raw/qN.json` lifts a completed
`get_amc_query_result` out of the session transcript (no retyping). Large results (q2): page with
`paged_query_result` limit 1000 and concatenate the saved pages into `raw/q2.json`.

Then: `tools/amc_ingest.py <folder> --brand "<Brand>"` → `tools/amc_findings.py <folder>`
→ `tools/build_amc_insights.py --findings <folder>/amc_findings.json --out-dir <folder>/pages` → `tools/amc_data_workbook.py`.
The builder writes four standalone pages plus `pages.json`:

| Page | Key | Content |
|---|---|---|
| New-to-Brand | new-to-brand | NTB by month and ad type, NTB search terms (queries 1, 2) |
| Repeat Purchase | repeat-purchase | SnS / repeat / one-time by month and by ASIN (queries 3, 4) |
| Path to Conversion | path-to-conversion | Ad types seen in the 30 days before purchase, by month (query 5) |
| Time to Conversion | time-to-conversion | Click-to-purchase timing by ad type (query 6) |

All four keys are in RESERVED_PAGES, so every account has the paths as placeholders until published.
Publish each entry of `pages.json` with
`python3 tools/publish_monthly.py page --repo . --client xps-<client> --brand "<Brand>" --key <key> --label "<label>" --file <folder>/pages/<file> --note "<note>"`.
Results go to the client Drive folder under `AMC/<yyyy-mm>`.

Known limitation: queries 3 and 4 count "repeat" against all orders since the run start, so early months have
less history than later ones. `3b_` / `4b_` (draft, not yet run) use a fixed 3-month lookback for every month.
Limit: 25 queries per rolling 24 hours across all accounts, 2 in flight. One account = 6 queries.

## Coverage check before the pack (added Nov 13, 2026)

Run query 1 (or the one-line coverage check below) first. AMC blanks the month on any row under ~100 shoppers,
so small accounts produce empty monthly pages. Run the full pack only when most months of the window are visible.

```sql
SELECT DATE_TRUNC('month', conversion_event_dt) AS month_start, COUNT(DISTINCT user_id) AS customers,
       SUM(total_purchases) AS purchases, SUM(total_product_sales) AS sales
FROM amazon_attributed_events_by_conversion_time WHERE total_purchases > 0 AND user_id IS NOT NULL GROUP BY 1
```

Jan – Sep 2026 result: Steam Clip 0 of 9 months visible, SkySail 1, Ultimate Washer 3, Joe's Trends 1 (AMC history from mid-2026),
Zesty Snackz 7, Smart Cookie 9, Sidekick 9, Southern Dental 9. Steam Clip, SkySail, Ultimate Washer and Joe's Trends stay without
AMC pages until volume clears the floor; Inglesina and SavonGoods are smaller still and were not run.
Limit in practice: 2 queries in flight across the whole MAP account, not per AMC instance.
