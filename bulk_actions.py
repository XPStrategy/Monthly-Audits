#!/usr/bin/env python3
"""Monthly Account Review: Amazon Ads bulk-upload files (Sponsored Products).

Usage: python3 bulk_actions.py <account_dir> --run-date YYYY-MM-DD [--brand-terms a,b] [--product-terms a,b]

Reads the bk_*.json MAP pulls in <account_dir> (see BULK_SQL in this file) plus st_top.json and
targets.json from the standard review pulls, and writes:
  <account_dir>/bulk/<slug>_<kind>_<yyyy-mm>.xlsx   one Amazon bulksheet per action set
  <account_dir>/bulk.json                         rows + rules for the review page
Every file is a 'Sponsored Products Campaigns' sheet in Amazon's bulksheet layout: IDs written as text,
informational metric columns filled for the reviewer (Amazon ignores them on upload).
Rules are fixed and derived from the account's own data; nothing is typed by hand.
"""
import argparse, collections, datetime as dt, json, math, os, re, statistics

HEAD = ["Product", "Entity", "Operation", "Campaign ID", "Ad Group ID", "Portfolio ID", "Ad ID", "Keyword ID",
        "Product Targeting ID", "Campaign Name", "Ad Group Name", "Campaign Name (Informational only)",
        "Ad Group Name (Informational only)", "Portfolio Name (Informational only)", "Start Date", "End Date",
        "Targeting Type", "State", "Campaign State (Informational only)", "Ad Group State (Informational only)",
        "Daily Budget", "SKU", "ASIN (Informational only)", "Eligibility Status (Informational only)",
        "Reason for Ineligibility (Informational only)", "Ad Group Default Bid", "Ad Group Default Bid (Informational only)",
        "Bid", "Keyword Text", "Native Language Keyword", "Native Language Locale", "Match Type", "Bidding Strategy",
        "Placement", "Percentage", "Product Targeting Expression",
        "Resolved Product Targeting Expression (Informational only)", "Audience ID", "Shopper Cohort Percentage",
        "Shopper Cohort Type", "Segment Name (Informational only)", "Sites", "Off-Amazon ad serving", "Video Asset ID",
        "Video Headline", "Video Description", "Video Optimized Text", "Video Status", "Impressions", "Clicks",
        "Click-through Rate", "Spend", "Sales", "Orders", "Units", "Conversion Rate", "ACOS", "CPC", "ROAS"]
TEXT_COLS = {"Campaign ID", "Ad Group ID", "Portfolio ID", "Ad ID", "Keyword ID", "Product Targeting ID", "SKU",
             "Start Date", "Keyword Text"}
ASIN_RE = re.compile(r"^b0[a-z0-9]{8}$")

# Lean MAP pulls this module needs (render with .format(**windows)); see the SKILL for the run order.
BULK_SQL = {
 "bk_harvest": """WITH s AS (SELECT lower(trim(searchTerm)) AS t, keywordType AS kt, CAST(adGroupId AS VARCHAR) AS g, CAST(campaignId AS VARCHAR) AS c, cost, sales14d AS sl, purchases14d AS o, clicks AS k FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}')
SELECT t, ROUND(SUM(cost),2) AS sp, ROUND(SUM(sl),2) AS sl, SUM(o) AS o, SUM(k) AS k, SUM(CASE WHEN kt IN ('TARGETING_EXPRESSION_PREDEFINED','BROAD','PHRASE') THEN o ELSE 0 END) AS o_src, SUM(CASE WHEN kt='EXACT' THEN o ELSE 0 END) AS o_ex, arg_max(g, o) AS g, arg_max(c, o) AS c, repeat('x', 1450) AS pad FROM s GROUP BY t HAVING SUM(o) >= 2 ORDER BY sl DESC""",
 "bk_neg": """WITH s AS (SELECT lower(trim(searchTerm)) AS t, keywordType AS kt, CAST(adGroupId AS VARCHAR) AS g, CAST(campaignId AS VARCHAR) AS c, campaignName AS cn, adGroupName AS gn, cost, purchases14d AS o, clicks AS k FROM sponsored_products_search_terms WHERE date BETWEEN '{W0}' AND '{W1}'),
tt AS (SELECT t, SUM(o) AS o, SUM(cost) AS sp FROM s GROUP BY t)
SELECT s.c, s.g, any_value(s.cn) AS cn, any_value(s.gn) AS gn, s.kt, s.t, ROUND(SUM(s.cost),2) AS sp, SUM(s.k) AS k, ROUND(any_value(tt.sp),2) AS t_sp, repeat('x', 400) AS pad FROM s JOIN tt ON s.t = tt.t WHERE tt.o = 0 AND tt.sp >= 25 GROUP BY s.c, s.g, s.kt, s.t HAVING SUM(s.k) > 0 ORDER BY t_sp DESC, sp DESC""",
 "bk_pads": """SELECT CAST(campaignId AS VARCHAR) AS c, CAST(adGroupId AS VARCHAR) AS g, advertisedAsin AS a, arg_max(advertisedSku, cost) AS sku, ROUND(SUM(cost),2) AS sp, ROUND(SUM(sales14d),2) AS sl, SUM(purchases14d) AS o, MAX(date) AS ld FROM sponsored_products_product_ads WHERE date BETWEEN '{S0}' AND '{L1}' GROUP BY 1,2,3""",
 "bk_camps": """SELECT CAST(campaignId AS VARCHAR) AS c, any_value(campaignName) AS cn, arg_max(campaignBudgetAmount, date) AS bud, arg_max(campaignStatus, date) AS st, MAX(date) AS ld, ROUND(SUM(CASE WHEN date >= '{L0}' THEN cost ELSE 0 END),2) AS sp30, ROUND(SUM(CASE WHEN date >= '{L0}' THEN sales14d ELSE 0 END),2) AS sl30, SUM(CASE WHEN date >= '{L0}' THEN purchases14d ELSE 0 END) AS o30, ROUND(SUM(cost),2) AS sp60, ROUND(SUM(sales14d),2) AS sl60, repeat('x', 500) AS pad FROM sponsored_products_campaigns WHERE date BETWEEN '{S0}' AND '{L1}' GROUP BY 1 HAVING SUM(cost) > 0 ORDER BY sp30 DESC""",
 "bk_sc": """SELECT childAsin AS a, ROUND(SUM(orderedProductSales_amount),2) AS s, SUM(unitsOrdered) AS u, SUM(totalOrderItems) AS o, SUM(sessions) AS ses, repeat('x', 5200) AS pad FROM sp_sales_traffic WHERE date BETWEEN '{S0}' AND '{L1}' GROUP BY 1 HAVING SUM(unitsOrdered) > 0 ORDER BY s DESC""",
 "bk_sqp": """WITH mx AS (SELECT MAX(endDate) AS e FROM sp_search_query_performance), w AS (SELECT lower(trim(searchQuery)) AS q, asin, SUM(asinPurchaseCount) AS p, SUM(asinClickCount) AS ck FROM sp_search_query_performance WHERE endDate > (SELECT e FROM mx) - INTERVAL 56 DAY GROUP BY 1,2)
SELECT q, SUM(p) AS bp, SUM(ck) AS bc, arg_max(asin, p) AS top_asin, MAX(p) AS top_p, (SELECT MAX(e) FROM mx) AS e, repeat('x', 1100) AS pad FROM w GROUP BY q HAVING SUM(p) >= 3 ORDER BY bp DESC""",
 "bk_skus": """SELECT asin, arg_max(sku, TRY_CAST(available AS INTEGER)) AS sku, any_value("product-name") AS name, arg_max(TRY_CAST(available AS INTEGER), "_loaded_at") AS avail FROM sp_fba_inventory_planning WHERE asin IN ({ASINS}) GROUP BY 1""",
}


def load(d, name, default=None):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return default
    x = json.load(open(p))
    if isinstance(x, dict) and "data" in x:
        x = x["data"]
    if isinstance(x, list):
        for r in x:
            r.pop("pad", None)
    return x


def load_live(d):
    """Live account state: Amazon bulk download (live_bulk.xlsx, enabled entities) or the live_*.json API pulls.
    Returns None when neither is in the folder."""
    p = os.path.join(d, "live_bulk.xlsx")
    if not os.path.exists(p):
        return None
    import openpyxl, warnings
    warnings.filterwarnings("ignore")
    ws = openpyxl.load_workbook(p, read_only=True)["Sponsored Products Campaigns"]
    it = ws.iter_rows(values_only=True); H = next(it)
    low = lambda x: (x or "").strip().lower()
    L = {"source": "Amazon Ads bulk download", "ad_groups": set(), "campaigns": {}, "neg_ag": set(), "neg_c": set(),
         "neg_pt": set(), "exact": set(), "pt": set(), "ad_asins": set()}
    for row in it:
        r = dict(zip(H, row)); e = r["Entity"]; st = low(r.get("State"))
        if e == "Campaign":
            L["campaigns"][r["Campaign ID"]] = r
        elif e == "Ad Group" and st == "enabled":
            L["ad_groups"].add(r["Ad Group ID"])
        elif e == "Negative Keyword":
            L["neg_ag"].add((r["Ad Group ID"], low(r["Keyword Text"]), low(r["Match Type"])))
        elif e == "Campaign Negative Keyword":
            L["neg_c"].add((r["Campaign ID"], low(r["Keyword Text"]), low(r["Match Type"])))
        elif e in ("Negative Product Targeting",):
            L["neg_pt"].add((r["Ad Group ID"], low(r["Product Targeting Expression"])))
        elif e == "Keyword" and st == "enabled" and low(r["Match Type"]) == "exact":
            L["exact"].add(low(r["Keyword Text"]))
        elif e == "Product Targeting" and st == "enabled":
            L["pt"].add(low(r["Product Targeting Expression"]))
        elif e == "Product Ad" and st == "enabled" and low(r.get("Ad Group State (Informational only)")) == "enabled" \
                and low(r.get("Campaign State (Informational only)")) == "enabled":
            L["ad_asins"].add(r["ASIN (Informational only)"])
    return L


def r2(v):
    return None if v is None else round(v + 1e-9, 2)


def write_bulk(path, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "Sponsored Products Campaigns"
    ws.append(HEAD)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F2937")
    idx = {h: i + 1 for i, h in enumerate(HEAD)}
    for n, r in enumerate(rows, start=2):
        for k, v in r.items():
            cell = ws.cell(row=n, column=idx[k], value=(str(v) if k in TEXT_COLS and v is not None else v))
            if k in TEXT_COLS:
                cell.number_format = "@"
    for col in ("Campaign ID", "Ad Group ID", "Campaign Name", "Ad Group Name", "Keyword Text", "Campaign Name (Informational only)",
                "Ad Group Name (Informational only)", "Product Targeting Expression"):
        ws.column_dimensions[ws.cell(row=1, column=idx[col]).column_letter].width = 34
    ws.freeze_panes = "A2"
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acct"); ap.add_argument("--run-date", required=True)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--brand-terms", default=""); ap.add_argument("--product-terms", default="")
    ap.add_argument("--min-weeks-cover", type=float, default=4.0)
    a = ap.parse_args(); D = a.acct
    run = dt.date.fromisoformat(a.run_date); mon = run.strftime("%Y-%m"); start = run.strftime("%Y%m%d")
    slug = a.slug or os.path.basename(os.path.normpath(D))
    brand = [t.strip().lower() for t in a.brand_terms.split(",") if t.strip()]
    prod_terms = [t.strip().lower() for t in a.product_terms.split(",") if t.strip()]

    camps = load(D, "bk_camps.json", []); pads = load(D, "bk_pads.json", []); hv = load(D, "bk_harvest.json", [])
    neg = load(D, "bk_neg.json", []); sc = load(D, "bk_sc.json", []); sqp = load(D, "bk_sqp.json", [])
    st = load(D, "st_top.json", []); tg = load(D, "targets.json", []); recs = load(D, "budget_recs_raw.json", {}) or {}
    skus_extra = load(D, "bk_skus.json", None) or load(D, "sku_extra.json", {}) or {}
    if isinstance(skus_extra, list):
        skus_extra = {r["asin"]: r for r in skus_extra}
    own_asins = {r["a"].lower() for r in pads} | {r["a"].lower() for r in sc}
    live = load_live(D)

    # ---------------- account references (all from data) ----------------
    sp60 = sum(r["sp60"] for r in camps); sl60 = sum(r["sl60"] for r in camps)
    T = sp60 / sl60 if sl60 else None
    sp30 = sum(r["sp30"] for r in camps); o30 = sum(r["o30"] for r in camps)
    CPA = sp30 / o30 if o30 else None
    pre = collections.Counter(r["cn"].split("|")[0].strip() for r in camps if "|" in r["cn"])
    prefix = pre.most_common(1)[0][0] if pre and pre.most_common(1)[0][1] >= 0.5 * len(camps) else ""
    nm = lambda *parts: " | ".join([p for p in ([prefix] if prefix else []) + list(parts)])
    camp_by = {r["c"]: r for r in camps}

    def cls(t):
        if ASIN_RE.match(t):
            return "Own ASIN" if t in own_asins else "ASIN"
        if any(b in t for b in brand):
            return "Branded"
        if any(p in t for p in prod_terms):
            return "Own product name"
        return "Generic"

    exact_cov = {(r["target"] or "").lower().strip() for r in tg if r.get("ktype") == "EXACT"}
    exact_cov |= {r["term"] for r in st if r.get("exact_covered")}
    exact_cov |= {r["t"] for r in hv if (r.get("o_ex") or 0) > 0}
    if live:
        exact_cov |= live["exact"]
    asin_targeted = {m.group(1) for r in tg if r.get("ktype") == "TARGETING_EXPRESSION"
                     for m in [re.search(r'asin(?:-expanded)?="?([a-z0-9]{10})', (r["target"] or "").lower())] if m}

    # ad group -> advertised ASINs (sales-weighted) and ASIN -> best SKU
    ag_asins = collections.defaultdict(list); sku_by = {}; sku_sp = collections.defaultdict(float)
    for r in pads:
        ag_asins[r["g"]].append(r)
        if r["sku"] and r["sp"] >= sku_sp[(r["a"], r["sku"])]:
            sku_sp[(r["a"], r["sku"])] = r["sp"]
    for (asin, sku), v in sorted(sku_sp.items(), key=lambda x: x[1]):
        sku_by[asin] = sku
    for asin, x in skus_extra.items():
        sku_by.setdefault(asin, x.get("sku"))
    sqp_top = {r["q"]: r for r in sqp}
    phrase_asin = {}
    for ph in prod_terms:
        hits = [r for r in sqp if ph in r["q"] and r.get("top_asin")]
        if hits:
            phrase_asin[ph] = max(hits, key=lambda r: r["bp"])["top_asin"]

    def asin_for(term, g):
        q = sqp_top.get(term)
        if q and q.get("top_asin"):
            return q["top_asin"], "Brand Analytics top ASIN"
        ph = [p for p in phrase_asin if p in term]
        if ph:
            return phrase_asin[max(ph, key=len)], "product name in query"
        rows = ag_asins.get(g, [])
        if len({r["a"] for r in rows}) == 1:
            return rows[0]["a"], "source ad group"
        if not rows:
            return None, "no product ad found"
        return None, "source ad group holds several ASINs"

    out = {"live_state": (live or {}).get("source", "report data only (no live campaign list)"), "run_date": a.run_date, "reference_acos": T, "reference_acos_source": "account SP ACoS, last 60 days",
           "cpa": CPA, "prefix": prefix, "files": {}, "notes": []}
    os.makedirs(os.path.join(D, "bulk"), exist_ok=True)
    fname = lambda k: f"{slug}_{k}_{mon}.xlsx"

    # ================= 1. Budgets =================
    rows_b, inc_b, exc_b = [], [], []
    for b in recs.get("constrained", []):
        c = camp_by.get(str(b["campaign_id"]), {})
        acos = (c.get("sp30") or 0) / c["sl30"] if c.get("sl30") else None
        lb = live["campaigns"].get(str(b["campaign_id"]), {}).get("Daily Budget") if live else None
        item = {"campaign_id": str(b["campaign_id"]), "campaign": c.get("cn", b["campaign_id"]), "budget": lb if lb is not None else c.get("bud"),
                "suggested": b["suggested"], "tib": b["tib"], "acos_l30": acos, "spend_l30": c.get("sp30"),
                "missed_sales": [b["missed_sales_lo"], b["missed_sales_hi"]]}
        if acos is not None and T and acos <= T and b["suggested"] > (item["budget"] or 0):
            inc_b.append(item)
            rows_b.append({"Product": "Sponsored Products", "Entity": "Campaign", "Operation": "Update",
                           "Campaign ID": item["campaign_id"], "Campaign Name (Informational only)": item["campaign"],
                           "Daily Budget": b["suggested"], "Spend": r2(c.get("sp30")), "Sales": r2(c.get("sl30")),
                           "Orders": c.get("o30"), "ACOS": r2(acos)})
        else:
            item["reason"] = "ACoS above reference" if acos is None or (T and acos > T) else "suggested budget not above current"
            exc_b.append(item)
    out["budgets"] = {"window": recs.get("window"), "checked": recs.get("checked"), "included": inc_b, "excluded": exc_b,
                      "rule": "Budget-constrained campaigns (time in budget below 100%) with last-30-day ACoS at or below the reference ACoS; daily budget set to Amazon's suggested budget."}
    if rows_b:
        write_bulk(os.path.join(D, "bulk", fname("budgets")), rows_b); out["files"]["budgets"] = fname("budgets")

    # ================= 2. Wasted spend: negatives =================
    stem = lambda t: " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in t.split())
    converting = {stem(r["t"]) for r in hv}
    by_term = collections.defaultdict(list)
    for r in neg:
        by_term[r["t"]].append(r)
    rows_n, inc_n, exc_n, seen = [], [], [], set()
    for t, rs in by_term.items():
        tot = rs[0]["t_sp"]; c_ = cls(t)
        if CPA is None or tot < CPA:
            continue
        clicks = sum(r["k"] for r in rs)
        if stem(t) in converting:
            exc_n.append({"term": t, "class": c_, "spend": tot, "clicks": clicks, "reason": "a singular/plural variant converts (negative exact also blocks close variants)"}); continue
        if c_ in ("Branded", "Own product name", "Own ASIN"):
            exc_n.append({"term": t, "class": c_, "spend": tot, "clicks": clicks, "reason": "own brand or product: listing or bid issue, not a negative"}); continue
        placed = 0
        for r in rs:
            if r["kt"] == "EXACT" and r["t"] == t:
                continue  # an Exact keyword on this exact term: pause the keyword instead (listed, not negated)
            key = (r["g"], t)
            if key in seen:
                continue
            if live:
                if r["g"] not in live["ad_groups"]:
                    continue
                if ASIN_RE.match(t) and (r["g"], f'asin="{t}"') in live["neg_pt"]:
                    continue
                if not ASIN_RE.match(t) and ((r["g"], t, "negative exact") in live["neg_ag"] or (r["c"], t, "negative exact") in live["neg_c"]):
                    continue
            seen.add(key); placed += 1
            base = {"Product": "Sponsored Products", "Operation": "Create", "Campaign ID": r["c"], "Ad Group ID": r["g"],
                    "Campaign Name (Informational only)": r["cn"], "Ad Group Name (Informational only)": r["gn"],
                    "State": "enabled", "Spend": r["sp"], "Clicks": r["k"], "Orders": 0}
            if ASIN_RE.match(t):
                rows_n.append({**base, "Entity": "Negative Product Targeting", "Product Targeting Expression": f'asin="{t.lower()}"'})
            else:
                rows_n.append({**base, "Entity": "Negative Keyword", "Keyword Text": t, "Match Type": "Negative Exact"})
        if not placed and live:
            exc_n.append({"term": t, "class": c_, "spend": tot, "clicks": clicks, "reason": "already negated in every enabled ad group where it spent"}); continue
        inc_n.append({"term": t, "class": c_, "spend": tot, "clicks": clicks, "ad_groups": placed,
                      "note": "" if placed else "only on an Exact keyword: pause that keyword"})
    inc_n.sort(key=lambda x: -x["spend"]); exc_n.sort(key=lambda x: -x["spend"])
    out["negatives"] = {"included": inc_n, "excluded": exc_n, "rows": len(rows_n), "spend": sum(x["spend"] for x in inc_n),
                        "rule": f"Search terms with zero orders whose spend reached at least one average order cost (SP cost per order, last 30 days: ${CPA:,.2f}) in the conversion-complete window. Added as negative exact in every ad group where the term spent; ASIN terms as negative product targets. Own-brand and own-product terms are listed, not negated."}
    if rows_n:
        write_bulk(os.path.join(D, "bulk", fname("negatives")), rows_n); out["files"]["negatives"] = fname("negatives")

    # ================= 3/4. Harvest (search terms, SQP) =================
    def harvest_block(cands, kind, label):
        groups = collections.OrderedDict(); rows = []; daily = 0.0
        cid = nm("SP", "Harvest", "Exact", label, mon)
        for x in cands:
            groups.setdefault(x["asin"], []).append(x); daily += x.get("daily_spend", 0)
        budget = max(10, int(math.ceil(daily * 1.2 / 5.0) * 5))
        rows.append({"Product": "Sponsored Products", "Entity": "Campaign", "Operation": "Create", "Campaign ID": cid,
                     "Campaign Name": cid, "Start Date": start, "Targeting Type": "Manual", "State": "enabled",
                     "Daily Budget": budget, "Bidding Strategy": "Dynamic bids - down only"})
        for asin, xs in groups.items():
            gid = f"{asin} | Exact"
            bids = sorted(x["bid"] for x in xs)
            rows.append({"Product": "Sponsored Products", "Entity": "Ad Group", "Operation": "Create", "Campaign ID": cid,
                         "Ad Group ID": gid, "Ad Group Name": gid, "State": "enabled", "Ad Group Default Bid": bids[len(bids) // 2]})
            rows.append({"Product": "Sponsored Products", "Entity": "Product Ad", "Operation": "Create", "Campaign ID": cid,
                         "Ad Group ID": gid, "SKU": sku_by.get(asin), "ASIN (Informational only)": asin, "State": "enabled"})
            for x in xs:
                base = {"Product": "Sponsored Products", "Operation": "Create", "Campaign ID": cid, "Ad Group ID": gid,
                        "State": "enabled", "Bid": x["bid"], "Spend": x.get("spend"), "Sales": x.get("sales"),
                        "Orders": x.get("orders"), "Clicks": x.get("clicks"), "ACOS": r2(x.get("acos"))}
                if ASIN_RE.match(x["term"]):
                    rows.append({**base, "Entity": "Product Targeting", "Product Targeting Expression": f'asin="{x["term"].lower()}"'})
                else:
                    rows.append({**base, "Entity": "Keyword", "Keyword Text": x["term"], "Match Type": "Exact"})
        missing = [g for g in groups if not sku_by.get(g)]
        write_bulk(os.path.join(D, "bulk", fname(kind)), rows); out["files"][kind] = fname(kind)
        return {"campaign": cid, "daily_budget": budget, "ad_groups": len(groups), "missing_sku": missing}

    hv_inc, hv_exc = [], []
    for r in hv:
        t = r["t"]; c_ = cls(t); acos = r["sp"] / r["sl"] if r["sl"] else None
        x = {"term": t, "class": c_, "orders": r["o"], "sales": r["sl"], "spend": r["sp"], "clicks": r["k"], "acos": acos,
             "src_orders": r["o_src"]}
        if r["o_src"] < 1:
            continue
        if t in exact_cov or (ASIN_RE.match(t) and (t in asin_targeted or (live and f'asin="{t}"' in live["pt"]))):
            continue
        if len(t) > 80:
            continue
        if acos is None or not T or acos > T:
            hv_exc.append({**x, "reason": "ACoS above reference"}); continue
        asin, how = asin_for(t, r["g"])
        if not asin:
            hv_exc.append({**x, "reason": how}); continue
        x.update(asin=asin, asin_source=how, bid=max(0.25, r2(r["sp"] / r["k"])) if r["k"] else 0.75, daily_spend=r["sp"] / 30.0)
        hv_inc.append(x)
    hv_inc.sort(key=lambda x: -x["sales"])
    out["harvest"] = {"included": hv_inc, "excluded": hv_exc,
                      "rule": "Search terms with 2+ orders converting from Auto, Broad or Phrase in the conversion-complete window, not on an Exact keyword with impressions in the last 60 days, ACoS at or below the reference ACoS. One new manual campaign, one ad group per ASIN (Brand Analytics top-purchase ASIN for the query, else the source ad group's top-sales ASIN). Bid = the term's average CPC."}
    if hv_inc:
        out["harvest"].update(harvest_block(hv_inc, "harvest_search_terms", "Search Terms"))

    exact_cpcs = [r["spd"] / r["clk"] for r in tg if r.get("ktype") == "EXACT" and (r.get("clk") or 0) >= 5]
    med_exact = r2(statistics.median(exact_cpcs)) if exact_cpcs else 1.0
    stmap = {r["term"]: r for r in st}; taken = {x["term"] for x in hv_inc}
    sq_inc = []
    for q in sqp:
        t = q["q"]
        if t in taken or t in exact_cov or ASIN_RE.match(t) or len(t) > 80 or not re.match(r"^[a-z0-9 &'.\-/]+$", t):
            continue
        s = stmap.get(t)
        if s and (s.get("cost") or 0) >= (CPA or 0) and (not s.get("sales") or s["cost"] / s["sales"] > T):
            continue   # already bought in ads above the reference ACoS: not a harvest
        ex = skus_extra.get(q["top_asin"], {})
        if ex.get("avail") is not None and ex["avail"] < 30:
            continue   # low FBA stock
        bid = r2(s["cost"] / s["clicks"]) if s and (s["clicks"] or 0) >= 3 else med_exact
        sq_inc.append({"term": t, "class": cls(t), "brand_purchases": q["bp"], "brand_clicks": q["bc"], "asin": q["top_asin"],
                       "asin_source": "Brand Analytics top ASIN", "bid": max(0.25, bid), "bid_source": "term CPC" if s and (s["clicks"] or 0) >= 3 else "median Exact CPC",
                       "paid_spend": s["cost"] if s else 0.0, "paid_orders": s["orders"] if s else 0,
                       "daily_spend": max(0.25, bid) * q["bc"] / 56.0 * 0.5})
    out["sqp_harvest"] = {"included": sq_inc, "window_end": sqp[0]["e"] if sqp else None,
                          "rule": "Brand Analytics queries with 3+ purchases of the brand's ASINs in the last 8 weeks, no Exact keyword with impressions in the last 60 days, not already in the search-term harvest file, not already bought in ads above the reference ACoS, ASIN not low on FBA stock. Daily budget sized to half of the brand's current daily clicks on these queries at the bid. Bid = the term's average CPC when it has 3+ paid clicks, else the account's median Exact CPC."}
    if sq_inc:
        out["sqp_harvest"].update(harvest_block(sq_inc, "harvest_sqp", "SQP"))

    # ================= 5. Products to push =================
    sp_asin = collections.defaultdict(float)
    for r in pads:
        sp_asin[r["a"]] += r["sp"]
    tot_sp = sum(sp_asin.values()) or 1; tot_s = sum(r["s"] for r in sc) or 1
    prods = []
    for r in sc:
        ratio = (sp_asin.get(r["a"], 0) / tot_sp) / (r["s"] / tot_s)
        ex = skus_extra.get(r["a"], {}); avail = ex.get("avail")
        wk = avail / (r["u"] / 60 * 7) if avail is not None and r["u"] else None
        prods.append({"asin": r["a"], "name": ex.get("name"), "sales_60": r["s"], "units_60": r["u"], "ad_spend_60": sp_asin.get(r["a"], 0.0),
                      "ratio": ratio, "available": avail, "weeks_cover": wk,
                      "live_ad": (r["a"] in live["ad_asins"]) if live else None,
                      "status": "No ad spend" if sp_asin.get(r["a"], 0) == 0 else ("Barely advertised" if ratio < 0.2 else ("Under-invested" if ratio < 0.7 else ""))})
    push = [p for p in prods if p["status"] in ("No ad spend", "Barely advertised") and p["sales_60"] >= 1000]
    for p in push:
        if p["available"] is None:
            p["file"] = False; p["reason"] = "no FBA stock record"
        elif p["weeks_cover"] is not None and p["weeks_cover"] < a.min_weeks_cover:
            p["file"] = False; p["reason"] = f"under {a.min_weeks_cover:.0f} weeks of FBA cover"
        elif not sku_by.get(p["asin"]):
            p["file"] = False; p["reason"] = "no SKU found"
        else:
            p["file"] = True
    in_file = [p for p in push if p["file"]]
    auto_cpcs = [r["spd"] / r["clk"] for r in tg if r.get("ktype") == "TARGETING_EXPRESSION_PREDEFINED" and (r.get("clk") or 0) >= 10]
    auto_bid = r2(statistics.median(auto_cpcs)) if auto_cpcs else 0.75
    out["products"] = {"rows": [p for p in prods if p["status"]], "push": push, "auto_bid": auto_bid,
                       "rule": "ASINs with $1,000+ total sales in the last 60 days and either no Sponsored Products spend or an ad-spend share below 0.2x their sales share. Included in the file only with 4+ weeks of FBA cover. One Auto campaign, one ad group per ASIN, default bid = the account's median Auto CPC."}
    if in_file:
        cid = nm("SP", "Auto", "Product Push", mon)
        rows = [{"Product": "Sponsored Products", "Entity": "Campaign", "Operation": "Create", "Campaign ID": cid, "Campaign Name": cid,
                 "Start Date": start, "Targeting Type": "Auto", "State": "enabled", "Daily Budget": 15 * len(in_file),
                 "Bidding Strategy": "Dynamic bids - down only"}]
        for p in in_file:
            gid = f"{p['asin']} | Auto"
            rows.append({"Product": "Sponsored Products", "Entity": "Ad Group", "Operation": "Create", "Campaign ID": cid, "Ad Group ID": gid,
                         "Ad Group Name": gid, "State": "enabled", "Ad Group Default Bid": auto_bid, "Sales": p["sales_60"]})
            rows.append({"Product": "Sponsored Products", "Entity": "Product Ad", "Operation": "Create", "Campaign ID": cid, "Ad Group ID": gid,
                         "SKU": sku_by[p["asin"]], "ASIN (Informational only)": p["asin"], "State": "enabled"})
        write_bulk(os.path.join(D, "bulk", fname("product_push")), rows); out["files"]["product_push"] = fname("product_push")
        out["products"].update(campaign=cid, daily_budget=15 * len(in_file))

    json.dump(out, open(os.path.join(D, "bulk.json"), "w"), indent=1, default=float)
    print(json.dumps({k: (len(v["included"]) if isinstance(v, dict) and "included" in v else None) for k, v in out.items() if isinstance(v, dict)}, indent=1))
    print("T", T, "CPA", CPA, "prefix", prefix, "files", out["files"])


if __name__ == "__main__":
    main()
