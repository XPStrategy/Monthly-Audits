# XP Strategy — Monthly Audits (internal)

Internal Monthly Account Reviews for existing XP Strategy clients, hosted on GitHub Pages.
One link per client; every month's review is added to the same link. XP team only, never sent to clients.

```
build_account_review.py   \
compute_account.py         |  the four review scripts. The xp-monthly-account-review skill
save.py                    |  downloads them from the repo ROOT by name. Never move or rename.
sql_templates.py          /
tools/publish_monthly.py   publishes one client's month into accounts/
accounts/<client>-<8 hex>/
  index.html               Home: one card per month, newest first (the link the AM opens)
  <yyyy-mm>.html           that month's review
  amc.html                 AMC Analysis (reserved: placeholder until published)
  links.json               months + links (Drive folder, consoles)
index.html                 blank landing page, lists nothing
robots.txt                 Disallow: /
```

`<client>` = the Slack channel name without `xps-` (`xps-cosmo-technologies` → `cosmo-technologies`).
The 8-hex suffix is fixed per client, so the link never changes.

## Where things live

| What | Where |
| --- | --- |
| Client folders | Google Drive: [XP Strategy - Internal Audits](https://drive.google.com/drive/folders/1dZfLdn8jovhQv2T8HOyx-WqoPHHJRgRT), one folder per `#xps-<client>` Slack channel, each with `Source` (run files by month) and `Old` |
| Channel ↔ folder ↔ MAP account map | `_Channel Map - Internal Audits` sheet in that Drive folder |
| Live pages | `https://xpstrategy.github.io/Monthly-Audits/accounts/<client>-<8 hex>/` |
| Communication | The client's own `#xps-<client>` Slack channel only. Claude drafts the post; a person approves before it sends |

## Every account already has a Home

All 29 `#xps-` channels have `accounts/<client>-<8 hex>/` with a Home page and an AMC placeholder,
even before their first review. The Drive folder holds `[LINK] <Brand> - XP Strategy - Internal Audit Page`
with the paths.

- New account: `python3 tools/publish_monthly.py init --repo . --client xps-<client> --brand "<Brand>" --drive-folder <id>`
- Extra page (AMC or any other): `python3 tools/publish_monthly.py page --repo . --client xps-<client> --brand "<Brand>" --key amc --label "AMC Analysis" --file amc.html`
- Category / Listing Review: `python3 tools/add_linkbar.py --repo . --client xps-<client> category.html listing.html`, then publish each with `page --key category-review --label "Category Review"` and `page --key listing-review --label "Listing Review"`. Both land under Category & SEO Reviews.
  The page appears under "Other Pages" on Home and in every page's Pages switcher. To reserve a new path
  for every account, add it to `RESERVED_PAGES` in the script and re-run `init`.

## Performance Overview (hub/performance.html)

Opens on **Month to date** (1st of the month through yesterday vs the same days of the month before); a toggle switches the
table to the last full month vs the month before. Columns: Total Sales, Ad Spend, Ad Sales, ACoS, TACoS.
The Monthly view of each account also shows the month-to-date row on top.
Click an account for its Weekly (last 24 weeks) / Monthly (last 24 months) / Annual table, with CSV downloads.
Same AM / PPC / status filters as the Account Hubs page.

Source: MerchantSpring (what clients see), US marketplace (UK for Nature Blends). Badass Moto is not in MerchantSpring and falls back to MAP.

**Current setup (decided Nov 25, 2026): ad columns from the Amazon Ads API on the XP PC, Total Sales from MerchantSpring via Claude.**
`pc/xp_performance/ads_pull.py` (run by `run_ads.ps1`, Task Scheduler Tuesday 6:00) pulls daily Ad Spend / Ad Sales
(SP + SB + SD, SP 14-day attribution by default) for the last 60 days with the budget bot's API credentials, and keeps
`history\ads_daily.json` on the PC because Amazon only keeps 60-95 days of report data. Credentials and the 23 US
accounts are read from `C:\XP\xp_budget_bot\config.json` (nothing copied); `config_ads.json` is optional, for accounts the
budget bot does not have (BingO, Altun, Sidekick, Nature Blends UK) and settings. Test: `run_ads.ps1 -Check`, then
`run_ads.ps1 -Only boroux`, then a full run. Next step: compare its numbers with MerchantSpring's ad columns before
the page switches over. The MerchantSpring API option below (`perf_pull.py`) stays ready in case XP gets an API key.

**MerchantSpring API option (no Claude tokens for the pull).** The XP PC pulls MerchantSpring through its API every Tuesday 6:00
(`pc/xp_performance/`, installed at `C:\XP\xp_performance`, same pattern as `xp_change_audit` and `xp_budget_bot`);
the publish step only builds, checks and pushes:

1. PC: `run_performance.ps1` (Task Scheduler) writes `output\<run date>\` and `perf_bundle_<run date>.zip`:
   `ms\<channelId>_W/_M/_MTD.json`, `manifest.json` (dates, per-store status), `check_month.json` / `check_mtd.json`
   (MerchantSpring's own per-store totals for reconciliation), `pull.log`.
2. Publish: `python3 tools/publish_performance.py --repo . --bundle <run folder or zip> [--raw <Badass Moto MAP folder>]`.
   Exit 0 = commit `hub/performance.html` and `hub/index.html` and push; exit 1 = do not publish, reasons printed.
3. Badass Moto is not in MerchantSpring: until it is, its 6 small MAP queries (below) go in `--raw`, or it shows as not connected.

PC setup (once): copy `pc/xp_performance` to `C:\XP\xp_performance`; `pip install tzdata`; set the key
(`[Environment]::SetEnvironmentVariable("MS_API_KEY", "<key>", "User")`, MerchantSpring > Settings > API, Owner/Admin only);
`run_performance.ps1 -Check`; then `register_task.ps1`. Keep `performance_stores.json` there in sync with `tools/`.

Reference, what the pull does (same calls as the MerchantSpring connector; one call at a time, parallel calls time out):

1. Per store (channel list in `MS_CHANNELS` in `tools/build_performance.py`), one call at a time (parallel calls time out):
   - Seller Central: `getSalesByPeriod`, includeTax=false, interval `w` (23 weeks + previousPeriod) and `M` (12 months + same 12 a year earlier)
   - Vendor Central: `getVendorSalesByPeriod` (orderedRevenue), same windows; `getSalesByPeriod` does not return ordered revenue for vendors
   - Save `{"currency", "rows": [{startTime, endTime, sales, priorSales, adSpend, priorAdSpend, adSales, priorAdSales}]}` as `<channelId>_W.json` / `<channelId>_M.json` in a folder outside the repo
   - Month to date: same tools, interval `d`, from the 1st of the month to yesterday, custom prior = the same days of the month before
     (interval `M` returns the full prior month, so it can't be used here). Save as `<channelId>_MTD.json`, same format.
   - Badass Moto (MAP): `ads_mtd.json` / `sp_mtd.json` with `g='D'` and `k` = `cur` / `prior` for the same two windows
2. `python3 tools/build_performance.py --repo . --ms <ms folder> --raw <MAP folder> --data-end <last Saturday> --mtd-end <yesterday>`
3. New account: add its MerchantSpring channelId to `MS_CHANNELS`.

## Monthly run (10th of each month)

1. Run `xp-monthly-account-review` for the account (MAP data, no manual input).
2. Publish: `python3 tools/publish_monthly.py --repo . --client <client> --brand "<Brand>" --month <yyyy-mm> --review <html> --drive-folder <id> --commit --push`
3. Save the run files (`config.json`, `findings.json`, MAP results) in the client's Drive folder `Source/<yyyy-mm>`.
4. Draft the `#xps-<client>` post (alert counts, lead alert, Home link); send after approval.

## Visibility

GitHub Pages is public to anyone holding a link, including for this public repo. Protection: fixed
random suffix per client, `noindex` on every page, `robots.txt`, a root page that lists nothing.
The Drive link on a page still needs an XP login. Never put notes about people,
pricing or credentials in a page or `links.json`. Raw MAP data stays in Drive.

## One-time setup

Settings → Pages → Source: Deploy from a branch, `main`, `/ (root)`. Needs a repo admin (CEO).

## Weekly Changes (hub/changes.html)

Password-protected page (for Tim and Abe): every account's Sponsored Products and Sponsored Brands changes over the
last 30 days, grouped into work sessions (no gap over 30 minutes; Bulk / tool = 50+ changes at 10+ per minute,
otherwise Hand edits). Click an account for its daily chart and session list, with CSV and print/PDF downloads.
Same AM / PPC / status filters as the Account Hubs page.

Source: Amazon Ads Change History API, pulled on the XP PC by `C:\XP\xp_change_audit\change_audit.py` (read-only,
same API credentials as the budget bot). Amazon's automatic out-of-budget toggles are left out; budget rules are
counted separately. Amazon does not record which user made a change.

- Data: `hub/changes-data.json`, an AES-256-GCM blob the page decrypts in the browser. Never commit unencrypted data.
- Weekly refresh: run the script, copy `output\changes-data.json` into `hub/`, commit and push. The page does not change.
- Page shell, filters and the budget-bot-name → hub-account map: `python3 tools/build_changes.py --repo .`
