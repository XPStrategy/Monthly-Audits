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
Then: `tools/amc_findings.py <folder>` → `tools/build_amc_insights.py --findings <folder>/amc_findings.json --out-dir <folder>/pages`
→ `tools/amc_data_workbook.py`. The builder writes one page per analysis plus `pages.json`:

| Page | Key | Content |
|---|---|---|
| AMC Analysis | amc (reserved) | Overview: KPIs, what the data shows, links to each analysis |
| AMC · New-to-Brand | amc-ntb | NTB by month and ad type, NTB search terms |
| AMC · Repeat Purchase | amc-repeat | SnS / repeat / one-time by month and by ASIN |
| AMC · Path to Conversion | amc-path | Ad types seen in the 30 days before purchase, by month |
| AMC · Time to Conversion | amc-ttc | Click-to-purchase timing by ad type |

Publish each entry of `pages.json` with
`python3 tools/publish_monthly.py page --repo . --client xps-<client> --brand "<Brand>" --key <key> --label "<label>" --file <folder>/pages/<file> --note "<note>"`.
Results go to the client Drive folder under `AMC/<yyyy-mm>`.
