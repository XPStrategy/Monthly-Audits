"""SQL templates for the MAP Monthly Account Review.

Every query carries a `pad` column so MAP returns the result as a saved file
(large results overflow to disk), which keeps raw rows out of the chat and
lets compute.py read them verbatim. Placeholders: {L0} {L1} {P0} {P1}
{LY0} {LY1} {H0} (history start) {Q0} {Q1} (LY Q4 window) {PAD}.
"""
# Run date 2026-10-20. L30 ends 3 days before the run date (report lag).
# W = conversion-lag window for Wasted Spend and Harvest: 30 days ending 14 days
# before the run date, so every click has had its full 14-day attribution window.
import datetime as _dt, json as _json, sys as _sys


def windows(run_date):
    """All windows derive from the run date (normally the 10th of the month)."""
    R = _dt.date.fromisoformat(run_date); d = lambda x: x.isoformat()
    L1 = R - _dt.timedelta(days=3); L0 = L1 - _dt.timedelta(days=29)
    P1 = L0 - _dt.timedelta(days=1); P0 = P1 - _dt.timedelta(days=29)
    W1 = R - _dt.timedelta(days=14); W0 = W1 - _dt.timedelta(days=29)
    lcm = (R.replace(day=1) - _dt.timedelta(days=1)).replace(day=1)          # last complete month
    y, m = lcm.year, lcm.month - 23
    while m <= 0:
        m += 12; y -= 1
    qy = R.year - 1                                                          # last year's Q4
    oct1 = _dt.date(qy, 10, 1); jan1 = _dt.date(qy + 1, 1, 1)
    Q0 = oct1 - _dt.timedelta(days=oct1.weekday()); Q1 = jan1 + _dt.timedelta(days=(6 - jan1.weekday()))
    return dict(L0=d(L0), L1=d(L1), P0=d(P0), P1=d(P1), LY0=d(L0 - _dt.timedelta(days=365)), LY1=d(L1 - _dt.timedelta(days=365)),
                W0=d(W0), W1=d(W1), H0=f"{y}-{m:02d}-01", Q0=d(Q0), Q1=d(Q1), D0=f"{qy}-10-01", D1=f"{qy}-12-31",
                LCM=lcm.strftime("%Y-%m"), QY=qy)


W = windows(_dt.date.today().isoformat())

ADS = {
# A. daily by ad type (12-month history where available)
"daily": """SELECT 'SP' AS ad_type, date, SUM(cost) AS cost, SUM(sales14d) AS sales, SUM(purchases14d) AS orders, SUM(clicks) AS clicks, SUM(impressions) AS impressions, repeat('x', {PAD}) AS pad FROM sponsored_products_campaigns WHERE date BETWEEN '{H0}' AND '{L1}' GROUP BY date
UNION ALL SELECT CASE WHEN COALESCE(video5SecondViews,0) + COALESCE(videoFirstQuartileViews,0) > 0 THEN 'SBV' ELSE 'SB' END, date, SUM(cost), SUM(sales), SUM(purchases), SUM(clicks), SUM(impressions), repeat('x', {PAD}) FROM sponsored_brands_campaigns WHERE date BETWEEN '{H0}' AND '{L1}' GROUP BY 1, date
UNION ALL SELECT 'SD', date, SUM(cost), SUM(sales), SUM(purchases), SUM(clicks), SUM(impressions), repeat('x', {PAD}) FROM sponsored_display_campaigns WHERE date BETWEEN '{H0}' AND '{L1}' GROUP BY date""",
# B. search terms, lag window, term level, with targeting-type split and exact coverage
"st_top": """WITH ex AS (SELECT DISTINCT lower(trim(keyword)) AS kw FROM sponsored_products_search_terms WHERE date BETWEEN '{P0}' AND '{L1}' AND keywordType='EXACT'),
st AS (SELECT lower(trim(searchTerm)) AS term, CASE WHEN keywordType='TARGETING_EXPRESSION_PREDEFINED' THEN 'AUTO' WHEN keywordType='TARGETING_EXPRESSION' THEN 'PT' ELSE keywordType END AS bucket, campaignName, cost, sales14d, purchases14d, clicks, impressions FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}')
SELECT term, SUM(cost) AS cost, SUM(sales14d) AS sales, SUM(purchases14d) AS orders, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
 SUM(CASE WHEN bucket='AUTO' THEN cost END) AS cost_auto, SUM(CASE WHEN bucket='AUTO' THEN purchases14d END) AS orders_auto,
 SUM(CASE WHEN bucket='BROAD' THEN cost END) AS cost_broad, SUM(CASE WHEN bucket='BROAD' THEN purchases14d END) AS orders_broad,
 SUM(CASE WHEN bucket='PHRASE' THEN cost END) AS cost_phrase, SUM(CASE WHEN bucket='PHRASE' THEN purchases14d END) AS orders_phrase,
 SUM(CASE WHEN bucket='EXACT' THEN cost END) AS cost_exact, SUM(CASE WHEN bucket='EXACT' THEN purchases14d END) AS orders_exact,
 SUM(CASE WHEN bucket='PT' THEN cost END) AS cost_pt, SUM(CASE WHEN bucket='PT' THEN purchases14d END) AS orders_pt,
 COUNT(DISTINCT campaignName) AS campaigns, arg_max(campaignName, cost) AS top_campaign,
 MAX(CASE WHEN term IN (SELECT kw FROM ex) THEN 1 ELSE 0 END) AS exact_covered, repeat('x', 200) AS pad
FROM st GROUP BY term ORDER BY cost DESC""",
# C. waste totals at search-term and target grain
"waste_totals": """WITH t AS (SELECT lower(trim(searchTerm)) AS term, SUM(cost) AS spd, SUM(purchases14d) AS o, SUM(clicks) AS c FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}' GROUP BY 1),
g AS (SELECT campaignName, adGroupName, keywordId, SUM(cost) AS spd, SUM(purchases14d) AS o, SUM(clicks) AS c FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}' GROUP BY 1,2,3)
SELECT 'term' AS grain, COUNT(*) AS n_all, SUM(spd) AS spend_all, SUM(CASE WHEN o=0 THEN spd END) AS waste_longtail, COUNT(CASE WHEN o=0 THEN 1 END) AS n_longtail, SUM(CASE WHEN o=0 AND c>=5 THEN spd END) AS waste_actionable, COUNT(CASE WHEN o=0 AND c>=5 THEN 1 END) AS n_actionable, repeat('x', {BIG}) AS pad FROM t
UNION ALL SELECT 'target', COUNT(*), SUM(spd), SUM(CASE WHEN o=0 THEN spd END), COUNT(CASE WHEN o=0 THEN 1 END), SUM(CASE WHEN o=0 AND (c>=5 OR spd>=5) THEN spd END), COUNT(CASE WHEN o=0 AND (c>=5 OR spd>=5) THEN 1 END), repeat('x', {BIG}) FROM g""",
# D. every SP + SB keyword/target, lag window (zero-order targets + keyword coverage)
"targets": """SELECT 'SP' AS ad_type, campaignName, adGroupName, keywordType AS ktype, COALESCE(keyword, targeting) AS target, SUM(cost) AS spd, SUM(sales14d) AS sls, SUM(purchases14d) AS ord, SUM(clicks) AS clk, SUM(impressions) AS imp, repeat('x', 300) AS pad FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}' GROUP BY 1,2,3,4,5
UNION ALL SELECT 'SB', campaignName, adGroupName, 'SB_' || matchType, keywordText, SUM(cost), SUM(sales), SUM(purchases), SUM(clicks), SUM(impressions), repeat('x', 300) FROM sponsored_brands_keywords WHERE date BETWEEN '{W0}' AND '{W1}' GROUP BY 1,2,3,4,5
ORDER BY spd DESC""",
# E. SP targeting-type buckets + placements, L30 vs P30
"alloc": """SELECT 'bucket' AS kind, CASE WHEN date>='{L0}' THEN 'L30' ELSE 'P30' END AS win, CASE WHEN keywordType='TARGETING_EXPRESSION_PREDEFINED' THEN 'Auto' WHEN keywordType='TARGETING_EXPRESSION' THEN 'Product/Category' WHEN keywordType='EXACT' THEN 'Exact' WHEN keywordType='PHRASE' THEN 'Phrase' WHEN keywordType='BROAD' THEN 'Broad' ELSE keywordType END AS name, SUM(cost) AS spd, SUM(sales14d) AS sls, SUM(purchases14d) AS ord, SUM(clicks) AS clk, SUM(impressions) AS imp, repeat('x', {BIG}) AS pad FROM sponsored_products_search_terms WHERE date BETWEEN '{P0}' AND '{L1}' GROUP BY 1,2,3
UNION ALL SELECT 'placement', CASE WHEN date>='{L0}' THEN 'L30' ELSE 'P30' END, placementClassification, SUM(cost), SUM(sales14d), SUM(purchases14d), SUM(clicks), SUM(impressions), repeat('x', {BIG}) FROM sponsored_products_campaign_placements WHERE date BETWEEN '{P0}' AND '{L1}' GROUP BY 1,2,3""",
# F. campaigns L30 vs P30
"campaigns": """WITH u AS (
SELECT 'SP' AS ad_type, campaignId, campaignName, date, cost, sales14d AS sales, purchases14d AS orders, clicks, impressions, campaignBudgetAmount AS budget, campaignStatus FROM sponsored_products_campaigns WHERE date BETWEEN '{P0}' AND '{L1}'
UNION ALL SELECT 'SB', campaignId, campaignName, date, cost, sales, purchases, clicks, impressions, campaignBudgetAmount, campaignStatus FROM sponsored_brands_campaigns WHERE date BETWEEN '{P0}' AND '{L1}'
UNION ALL SELECT 'SD', campaignId, campaignName, date, cost, sales, purchases, clicks, impressions, campaignBudgetAmount, campaignStatus FROM sponsored_display_campaigns WHERE date BETWEEN '{P0}' AND '{L1}')
SELECT ad_type, CAST(campaignId AS VARCHAR) AS campaign_id, campaignName,
 SUM(CASE WHEN date>='{L0}' THEN cost ELSE 0 END) AS spd_l30, SUM(CASE WHEN date>='{L0}' THEN sales ELSE 0 END) AS sls_l30, SUM(CASE WHEN date>='{L0}' THEN orders ELSE 0 END) AS ord_l30, SUM(CASE WHEN date>='{L0}' THEN clicks ELSE 0 END) AS clk_l30, SUM(CASE WHEN date>='{L0}' THEN impressions ELSE 0 END) AS imp_l30,
 SUM(CASE WHEN date<'{L0}' THEN cost ELSE 0 END) AS spd_p30, SUM(CASE WHEN date<'{L0}' THEN sales ELSE 0 END) AS sls_p30, SUM(CASE WHEN date<'{L0}' THEN orders ELSE 0 END) AS ord_p30, SUM(CASE WHEN date<'{L0}' THEN clicks ELSE 0 END) AS clk_p30,
 arg_max(budget, date) AS budget, arg_max(campaignStatus, date) AS status, MAX(date) AS last_date, repeat('x', 300) AS pad
FROM u GROUP BY 1,2,3 HAVING SUM(cost) > 0 ORDER BY spd_l30 DESC""",
# G. advertised products L30 vs P30
"products": """SELECT advertisedAsin AS asin,
 SUM(CASE WHEN date<'{L0}' THEN cost END) AS spd_p30, SUM(CASE WHEN date<'{L0}' THEN sales14d END) AS sls_p30, SUM(CASE WHEN date<'{L0}' THEN clicks END) AS clk_p30, SUM(CASE WHEN date<'{L0}' THEN purchases14d END) AS ord_p30,
 SUM(CASE WHEN date>='{L0}' THEN cost END) AS spd_l30, SUM(CASE WHEN date>='{L0}' THEN sales14d END) AS sls_l30, SUM(CASE WHEN date>='{L0}' THEN clicks END) AS clk_l30, SUM(CASE WHEN date>='{L0}' THEN purchases14d END) AS ord_l30, repeat('x', 1500) AS pad
FROM sponsored_products_product_ads WHERE date BETWEEN '{P0}' AND '{L1}' GROUP BY 1 ORDER BY COALESCE(spd_l30,0) DESC""",
}

SC = {
# I. monthly total sales, 24 months
"sc_monthly": """SELECT strftime(date, '%Y-%m') AS mon, SUM(orderedProductSales_amount) AS total_sales, SUM(unitsOrdered) AS units, SUM(sessions) AS sessions, SUM(totalOrderItems) AS orders, COUNT(DISTINCT date) AS days, repeat('x', 3000) AS pad FROM sp_sales_traffic WHERE date >= '{H0}' AND date <= '{L1}' GROUP BY 1 ORDER BY 1""",
# J. windows totals + per-ASIN
"sc_windows": """SELECT 'total' AS kind, CASE WHEN date >= '{L0}' AND date <= '{L1}' THEN 'L30' WHEN date >= '{P0}' AND date <= '{P1}' THEN 'P30' ELSE 'L30_LY' END AS win, NULL AS asin, SUM(orderedProductSales_amount) AS sales, SUM(unitsOrdered) AS units, SUM(sessions) AS sessions, repeat('x', 4000) AS pad FROM sp_sales_traffic WHERE (date >= '{P0}' AND date <= '{L1}') OR (date >= '{LY0}' AND date <= '{LY1}') GROUP BY 1,2,3
UNION ALL SELECT 'asin', CASE WHEN date >= '{L0}' THEN 'L30' ELSE 'P30' END, childAsin, SUM(orderedProductSales_amount), SUM(unitsOrdered), SUM(sessions), repeat('x', 4000) FROM sp_sales_traffic WHERE date BETWEEN '{P0}' AND '{L1}' GROUP BY 1,2,3""",
# K. inventory planning, latest pull per SKU
"inventory": """WITH latest AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY sku ORDER BY "_loaded_at" DESC) AS rn FROM sp_fba_inventory_planning)
SELECT asin, sku, "product-name" AS name, TRY_CAST(available AS INTEGER) AS available, TRY_CAST("inbound-quantity" AS INTEGER) AS inbound, TRY_CAST("Total Reserved Quantity" AS INTEGER) AS reserved, TRY_CAST("units-shipped-t30" AS INTEGER) AS units_t30, TRY_CAST("units-shipped-t7" AS INTEGER) AS units_t7, "fba-inventory-level-health-status" AS health, alert, "Recommended ship-in quantity" AS ship_in_qty, "Recommended ship-in date" AS ship_in_date, repeat('x', 1500) AS pad
FROM latest WHERE rn=1 AND (TRY_CAST("units-shipped-t30" AS INTEGER) > 0 OR TRY_CAST(available AS INTEGER) > 0) ORDER BY units_t30 DESC NULLS LAST""",
# L. search query performance, last 4 weeks available
"sqp": """WITH mx AS (SELECT MAX(endDate) AS e FROM sp_search_query_performance),
w AS (SELECT searchQuery, endDate, MAX(searchQueryVolume) AS vol, MAX(totalPurchaseCount) AS tot_p, MAX(totalClickCount) AS tot_c, MAX(totalQueryImpressionCount) AS tot_i, SUM(asinPurchaseCount) AS my_p, SUM(asinClickCount) AS my_c, SUM(asinImpressionCount) AS my_i
FROM sp_search_query_performance WHERE endDate > (SELECT e FROM mx) - INTERVAL 28 DAY GROUP BY 1,2)
SELECT lower(trim(searchQuery)) AS query, COUNT(*) AS weeks, SUM(vol) AS volume, SUM(tot_p) AS total_purchases, SUM(my_p) AS brand_purchases, SUM(tot_c) AS total_clicks, SUM(my_c) AS brand_clicks, SUM(tot_i) AS total_impr, SUM(my_i) AS brand_impr, MIN(endDate) AS w0, MAX(endDate) AS w1, repeat('x', 300) AS pad
FROM w GROUP BY 1 ORDER BY total_purchases DESC""",
# M. last-year Q4 weekly + top days
"ly_q4": """SELECT 'week' AS kind, CAST(date_trunc('week', date) AS VARCHAR) AS k, SUM(orderedProductSales_amount) AS sales, SUM(unitsOrdered) AS units, repeat('x', 4000) AS pad FROM sp_sales_traffic WHERE date BETWEEN '{Q0}' AND '{Q1}' GROUP BY 1,2
UNION ALL SELECT 'day', CAST(date AS VARCHAR), SUM(orderedProductSales_amount), SUM(unitsOrdered), repeat('x', 4000) FROM sp_sales_traffic WHERE date BETWEEN '{D0}' AND '{D1}' GROUP BY 1,2""",
}


def render(name, pad=3000, big=60000, w=None):
    src = ADS.get(name) or SC[name]
    return src.format(PAD=pad, BIG=big, **(w or W))

ADS["strategy"] = """WITH own AS (SELECT DISTINCT lower(advertisedAsin) AS a FROM sponsored_products_product_ads WHERE date BETWEEN '{P0}' AND '{L1}'),
x AS (SELECT keywordType AS kt, lower(COALESCE(keyword, targeting)) AS t, keywordId, cost, sales14d AS s, purchases14d AS o, clicks AS c, impressions AS i FROM sponsored_products_search_terms WHERE date BETWEEN '{L0}' AND '{L1}'
 UNION ALL SELECT 'SB', lower(keywordText), keywordId, cost, sales, purchases, clicks, impressions FROM sponsored_brands_keywords WHERE date BETWEEN '{L0}' AND '{L1}'),
y AS (SELECT *, regexp_extract(t, 'asin(-expanded)?="?([a-z0-9]{{10}})', 2) AS tasin FROM x)
SELECT CASE WHEN kt='TARGETING_EXPRESSION_PREDEFINED' THEN 'Auto Discovery'
 WHEN kt='TARGETING_EXPRESSION' AND tasin <> '' AND tasin IN (SELECT a FROM own) THEN 'Brand Defense (own ASINs)'
 WHEN kt='TARGETING_EXPRESSION' AND tasin <> '' THEN 'Competitor Conquest (ASINs)'
 WHEN kt='TARGETING_EXPRESSION' THEN 'Category Targeting'
 WHEN regexp_matches(t, '{BRAND_RE}') THEN 'Branded Keywords'
 WHEN regexp_matches(t, '{COMP_RE}') THEN 'Competitor Keywords'
 ELSE 'Generic Keywords' END AS strategy,
 COUNT(DISTINCT keywordId) AS targets, SUM(cost) AS spend, SUM(s) AS sales, SUM(o) AS orders, SUM(c) AS clicks, SUM(i) AS impressions, repeat('x', 20000) AS pad
FROM y GROUP BY 1 ORDER BY spend DESC"""

ADS["camp_bucket"] = """SELECT campaignName, CASE WHEN keywordType='TARGETING_EXPRESSION_PREDEFINED' THEN 'Auto' WHEN keywordType='TARGETING_EXPRESSION' AND lower(targeting) LIKE 'category=%' THEN 'Category' WHEN keywordType='TARGETING_EXPRESSION' THEN 'Product (ASIN)' WHEN keywordType='EXACT' THEN 'Exact' WHEN keywordType='PHRASE' THEN 'Phrase' WHEN keywordType='BROAD' THEN 'Broad' ELSE keywordType END AS bucket, SUM(cost) AS spd, repeat('x', 300) AS pad
FROM sponsored_products_search_terms WHERE date BETWEEN '{L0}' AND '{L1}' GROUP BY 1,2 HAVING SUM(cost) > 0 ORDER BY spd DESC"""


def render_strategy(brand_re, comp_re, w=None):
    return ADS["strategy"].format(BRAND_RE=brand_re, COMP_RE=comp_re, **(w or W))


def init_config(path, run_date, **kw):
    """Write config.json for one account with every window filled from the run date."""
    w = windows(run_date)
    cfg = {"slug": kw.get("slug"), "marketplace": kw.get("marketplace", "US"),
           "l30": [w["L0"], w["L1"]], "p30": [w["P0"], w["P1"]], "ly": [w["LY0"], w["LY1"]], "lag": [w["W0"], w["W1"]],
           "report_date": run_date, "last_complete_month": w["LCM"], "q4_year": w["QY"],
           "display_brand": kw.get("display_brand"), "ads_account_id": kw.get("ads_account_id"),
           "sp_account_id": kw.get("sp_account_id"), "brand_terms": kw.get("brand_terms", []),
           "competitor_terms": kw.get("competitor_terms", []), "notes": kw.get("notes", [])}
    _json.dump(cfg, open(path, "w"), indent=1)
    return cfg


if __name__ == "__main__":
    # python3 sql_templates.py <run_date> windows                        -> every window as JSON
    # python3 sql_templates.py <run_date> <query_name>                   -> rendered SQL
    # python3 sql_templates.py <run_date> strategy <config.json>         -> strategy SQL with brand/competitor terms
    run, name = _sys.argv[1], _sys.argv[2]; w = windows(run)
    if name == "windows":
        print(_json.dumps(w, indent=1))
    elif name == "strategy":
        import re as _re
        c = _json.load(open(_sys.argv[3]))
        rx = lambda xs: "|".join(_re.escape(x).replace("'", "''") for x in xs)
        print(render_strategy(rx(c["brand_terms"]), rx(c["competitor_terms"]), w))
    else:
        print(render(name, w=w))

