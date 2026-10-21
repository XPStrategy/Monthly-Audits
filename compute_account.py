#!/usr/bin/env python3
"""MAP Monthly Account Review — deterministic calculation layer (any account).

Usage: python3 compute_account.py <run_dir>/<slug>
Reads the raw MAP pulls in that folder (see sql_templates.py) plus config.json
and budget_recs.json, writes findings.json there. Seller Central files are
optional: without them, total-sales, TACoS, inventory, SQP and LY views are
marked unavailable instead of estimated.
"""
import json, os, re, sys, datetime as dt
from collections import defaultdict

CFG = {"actionable_clicks": 5, "harvest_min_orders": 2, "prime_clicks": 30, "prime_acos": 0.40,
       "strong_acos": 0.60, "max_term_len": 80, "sqp_rows": 25, "campaign_rows": 60, "product_rows": 15}


def div(a, b):
    return a / b if (a is not None and b) else None


def chg(new, old):
    return (new - old) / old if (old not in (None, 0) and new is not None) else None


def main(acct):
    def load(name, required=True):
        p = os.path.join(acct, name)
        if not os.path.exists(p):
            if required:
                raise SystemExit(f"missing {p}")
            return None
        d = json.load(open(p))
        if isinstance(d, dict) and d.get("status") == "success":
            for r in d["data"]:
                r.pop("pad", None)
            return d["data"]
        return d

    cfg = load("config.json")
    l0, l1 = cfg["l30"]; p0, p1 = cfg["p30"]; y0, y1 = cfg["ly"]
    w0, w1 = cfg.get("lag", cfg["l30"])
    brand_terms = [t.lower() for t in cfg["brand_terms"]]
    comp_terms = [t.lower() for t in cfg["competitor_terms"]]
    daily = load("daily.json"); st = load("st_top.json"); wt_rows = load("waste_totals.json")
    tgts = load("targets.json"); alloc_rows = load("alloc.json"); camps = load("campaigns.json")
    prods = load("products.json"); cb = load("camp_bucket.json"); strat_rows = load("strategy.json")
    budget = load("budget_recs.json", False) or {"window": None, "checked": 0, "constrained": []}
    has_sc = os.path.exists(os.path.join(acct, "sc_windows.json"))
    scm = load("sc_monthly.json", False); scw = load("sc_windows.json", False)
    inv_rows = load("inventory.json", False); sqp = load("sqp.json", False); lyq = load("ly_q4.json", False)

    def is_brand(t):
        return any(b in t.lower() for b in brand_terms)

    def is_comp(t):
        return any(c in t.lower() for c in comp_terms)

    def classify(term):
        t = term.lower()
        if len(t) == 10 and t.startswith("b0") and t.isalnum():
            return "ASIN"
        if is_brand(t):
            return "Own brand"
        if is_comp(t):
            return "Competitor"
        return "Generic"

    def sum_rows(rows):
        t = defaultdict(float)
        for r in rows:
            for k in ("cost", "sales", "orders", "clicks", "impressions"):
                t[k] += r.get(k) or 0
        return t

    def ad_metrics(t):
        return {"spend": t["cost"], "sales": t["sales"], "orders": t["orders"], "clicks": t["clicks"],
                "impressions": t["impressions"], "acos": div(t["cost"], t["sales"]), "roas": div(t["sales"], t["cost"]),
                "cpc": div(t["cost"], t["clicks"]), "ctr": div(t["clicks"], t["impressions"]), "cvr": div(t["orders"], t["clicks"])}

    # ------------------------------------------------ Seller Central windows
    W = {}
    asin_sc = defaultdict(dict)
    if scw:
        for r in scw:
            if r["kind"] == "total":
                W[r["win"]] = {"total_sales": r["sales"], "units": r["units"], "sessions": r["sessions"]}
            else:
                asin_sc[r["asin"]][r["win"]] = r
    tsL, tsP, tsY = W.get("L30"), W.get("P30"), W.get("L30_LY")

    # ------------------------------------------------ period comparison ----
    L = ad_metrics(sum_rows([r for r in daily if l0 <= r["date"] <= l1]))
    P = ad_metrics(sum_rows([r for r in daily if p0 <= r["date"] <= p1]))
    has_ly_ads = bool(daily) and min(r["date"] for r in daily if (r["cost"] or 0) > 0) <= y0
    Y = ad_metrics(sum_rows([r for r in daily if y0 <= r["date"] <= y1])) if has_ly_ads else None
    gy = lambda k: Y[k] if Y else None
    rows = []

    def add(key, label, fmt, l, p, y=None, better="up"):
        is_pts = fmt == "pct"
        rows.append({"key": key, "label": label, "fmt": fmt, "l30": l, "p30": p, "ly": y,
                     "mom": (l - p) if is_pts and l is not None and p is not None else chg(l, p),
                     "yoy": ((l - y) if is_pts and l is not None else chg(l, y)) if y is not None else None,
                     "better": better})
    g = lambda w, k: (w or {}).get(k)
    if has_sc:
        add("total_sales", "Total Sales", "money", g(tsL, "total_sales"), g(tsP, "total_sales"), g(tsY, "total_sales"))
        add("units", "Units Ordered", "int", g(tsL, "units"), g(tsP, "units"), g(tsY, "units"))
        add("sessions", "Sessions", "int", g(tsL, "sessions"), g(tsP, "sessions"), g(tsY, "sessions"))
        add("unit_session", "Unit Session %", "pct", div(g(tsL, "units"), g(tsL, "sessions")),
            div(g(tsP, "units"), g(tsP, "sessions")), div(g(tsY, "units"), g(tsY, "sessions")))
        add("asp", "Avg Selling Price", "money2", div(g(tsL, "total_sales"), g(tsL, "units")),
            div(g(tsP, "total_sales"), g(tsP, "units")), div(g(tsY, "total_sales"), g(tsY, "units")))
    add("spend", "Ad Spend", "money", L["spend"], P["spend"], gy("spend"), better="neutral")
    add("ad_sales", "Ad Sales", "money", L["sales"], P["sales"], gy("sales"))
    add("acos", "ACoS", "pct", L["acos"], P["acos"], gy("acos"), better="down")
    if has_sc:
        add("tacos", "TACoS", "pct", div(L["spend"], g(tsL, "total_sales")), div(P["spend"], g(tsP, "total_sales")),
            div(gy("spend"), g(tsY, "total_sales")), better="down")
        add("ad_share", "Ad Sales % of Total", "pct", div(L["sales"], g(tsL, "total_sales")), div(P["sales"], g(tsP, "total_sales")),
            div(gy("sales"), g(tsY, "total_sales")), better="neutral")
    add("roas", "ROAS", "x", L["roas"], P["roas"], gy("roas"))
    add("cpc", "CPC", "money2", L["cpc"], P["cpc"], gy("cpc"), better="down")
    add("ctr", "CTR", "pct2", L["ctr"], P["ctr"], gy("ctr"))
    add("cvr", "Ad CVR", "pct2", L["cvr"], P["cvr"], gy("cvr"))
    add("impressions", "Impressions", "int", L["impressions"], P["impressions"], gy("impressions"))
    add("clicks", "Clicks", "int", L["clicks"], P["clicks"], gy("clicks"))
    add("orders", "Ad Orders", "int", L["orders"], P["orders"], gy("orders"))
    for r in rows:
        if r["fmt"] == "pct2":
            r["mom"] = chg(r["l30"], r["p30"])
            r["yoy"] = chg(r["l30"], r["ly"]) if r["ly"] is not None else None

    # ------------------------------------------------ 24 months ------------
    tsm = {m["mon"]: m for m in (scm or [])}
    by_mon = defaultdict(list)
    for r in daily:
        by_mon[r["date"][:7]].append(r)
    first_by_type = {}
    for r in daily:
        if (r["cost"] or 0) > 0:
            first_by_type[r["ad_type"]] = min(first_by_type.get(r["ad_type"], "9999"), r["date"])
    ad_start = first_by_type.get("SP", min(first_by_type.values()) if first_by_type else "9999")
    ad_start_month = ad_start[:7] if ad_start.endswith("-01") else (
        (dt.date.fromisoformat(ad_start[:7] + "-01") + dt.timedelta(days=32)).strftime("%Y-%m"))
    # SP alone defines the start when another ad type started later but SP history is longer
    sp_first = first_by_type.get("SP", "9999")
    end_m = dt.date.fromisoformat(cfg["last_complete_month"] + "-01")
    months = []
    for i in range(23, -1, -1):
        y, m = end_m.year, end_m.month - i
        while m <= 0:
            m += 12; y -= 1
        mon = f"{y}-{m:02d}"; ly = f"{y-1}-{m:02d}"
        t = tsm.get(mon, {}); tl = tsm.get(ly, {})
        row = {"month": mon, "total_sales": t.get("total_sales"), "total_sales_ly": tl.get("total_sales"),
               "units": t.get("units"), "sessions": t.get("sessions"), "unit_session": div(t.get("units"), t.get("sessions"))}
        row["yoy"] = chg(row["total_sales"], row["total_sales_ly"])
        if mon >= ad_start_month:
            am = ad_metrics(sum_rows(by_mon[mon]))
            row.update({"spend": am["spend"], "ad_sales": am["sales"], "acos": am["acos"], "cpc": am["cpc"],
                        "ctr": am["ctr"], "cvr": am["cvr"], "roas": am["roas"], "tacos": div(am["spend"], row["total_sales"])})
        months.append(row)

    end = dt.date.fromisoformat(l1); weekly = []
    for i in range(12, -1, -1):
        we = end - dt.timedelta(days=7 * i); ws = we - dt.timedelta(days=6)
        m = ad_metrics(sum_rows([r for r in daily if ws.isoformat() <= r["date"] <= we.isoformat()]))
        m["week_start"], m["week_end"] = ws.isoformat(), we.isoformat()
        weekly.append(m)

    # ------------------------------------------------ allocation -----------
    def blk(spd, sls, o, c, i):
        return {"spend": spd, "sales": sls, "orders": o, "clicks": c, "impressions": i,
                "acos": div(spd, sls), "cvr": div(o, c), "cpc": div(spd, c), "ctr": div(c, i)}
    empty = blk(0, 0, 0, 0, 0)

    def alloc(items):
        tl = sum(x["l30"]["spend"] for x in items) or 1; tp = sum(x["p30"]["spend"] for x in items) or 1
        sl = sum(x["l30"]["sales"] for x in items) or 1
        for x in items:
            x["share_l30"] = x["l30"]["spend"] / tl; x["share_p30"] = x["p30"]["spend"] / tp
            x["sales_share_l30"] = x["l30"]["sales"] / sl
        return items
    ad_type = []
    for at, nm in (("SP", "Sponsored Products"), ("SB", "Sponsored Brands"), ("SBV", "Sponsored Brands Video"), ("SD", "Sponsored Display")):
        a = ad_metrics(sum_rows([r for r in daily if r["ad_type"] == at and l0 <= r["date"] <= l1]))
        b = ad_metrics(sum_rows([r for r in daily if r["ad_type"] == at and p0 <= r["date"] <= p1]))
        if True:
            ad_type.append({"name": nm, "l30": blk(a["spend"], a["sales"], a["orders"], a["clicks"], a["impressions"]),
                            "p30": blk(b["spend"], b["sales"], b["orders"], b["clicks"], b["impressions"])})
    alloc(ad_type)
    grp = defaultdict(dict)
    for r in alloc_rows:
        grp[(r["kind"], r["name"])][r["win"]] = blk(r["spd"], r["sls"], r["ord"], r["clk"], r["imp"])
    tmap = {"Automatic": "Auto", "Broad": "Broad", "Phrase": "Phrase", "Exact": "Exact", "Product Targeting": "Product/Category"}
    targeting = alloc([{"name": n, "l30": grp.get(("bucket", k), {}).get("L30", empty), "p30": grp.get(("bucket", k), {}).get("P30", empty)}
                       for n, k in tmap.items()])
    pl_map = {"Top of Search on-Amazon": "Top of Search", "Other on-Amazon": "Rest of Search",
              "Detail Page on-Amazon": "Product Pages", "Off Amazon": "Off Amazon"}
    pl = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
    for (kind, n), wins in grp.items():
        if kind != "placement" or n not in pl_map:
            continue
        for w, b in wins.items():
            pl[pl_map[n]][w] = [b["spend"], b["sales"], b["orders"], b["clicks"], b["impressions"]]
    placements = alloc([{"name": n, "l30": blk(*pl[n]["L30"]), "p30": blk(*pl[n]["P30"])}
                        for n in ("Top of Search", "Rest of Search", "Product Pages", "Off Amazon")])

    # ------------------------------------------------ strategy mix ---------
    order = ["Branded Keywords", "Brand Defense (own ASINs)", "Generic Keywords", "Category Targeting",
             "Competitor Keywords", "Competitor Conquest (ASINs)", "Auto Discovery"]
    sd = {r["strategy"]: r for r in strat_rows}
    tot_sp = sum(r["spend"] or 0 for r in strat_rows); tot_sl = sum(r["sales"] or 0 for r in strat_rows)
    strategy_mix = [{"name": s, "spend": sd[s]["spend"], "sales": sd[s]["sales"], "orders": sd[s]["orders"],
                     "clicks": sd[s]["clicks"], "targets": sd[s]["targets"], "share": sd[s]["spend"] / tot_sp,
                     "sales_share": (sd[s]["sales"] or 0) / tot_sl if tot_sl else None,
                     "acos": div(sd[s]["spend"], sd[s]["sales"]), "cvr": div(sd[s]["orders"], sd[s]["clicks"]),
                     "cpc": div(sd[s]["spend"], sd[s]["clicks"])} for s in order if s in sd]

    # ------------------------------------------------ campaigns ------------
    ctype_spend = defaultdict(lambda: defaultdict(float))
    for r in cb:
        ctype_spend[r["campaignName"]][r["bucket"]] += r["spd"] or 0
    tib = {str(b["campaign_id"]): b for b in budget["constrained"]}
    campaigns = []
    for c in camps:
        cs = ctype_spend.get(c["campaignName"])
        if c["ad_type"] != "SP":
            ctype = {"SB": "Sponsored Brands", "SD": "Sponsored Display"}[c["ad_type"]]
        elif cs:
            ctype = max(cs, key=cs.get)
            if cs[ctype] / sum(cs.values()) < 0.8:
                ctype = "Mixed"
        else:
            ctype = "Unclassified"
        a = div(c["spd_l30"], c["sls_l30"]); flags = []
        if c["spd_l30"] >= 100 and c["ord_l30"] == 0:
            flags.append("No orders")
        if a is not None and a > 1:
            flags.append("ACoS > 100%")
        if str(c["campaign_id"]) in tib:
            flags.append(f"Time in budget {round(tib[str(c['campaign_id'])]['tib']*100)}%")
        campaigns.append({"ad_type": c["ad_type"], "id": str(c["campaign_id"]), "name": c["campaignName"], "type": ctype,
                          "status": c["status"], "budget": c["budget"], "spend_l30": c["spd_l30"], "spend_p30": c["spd_p30"],
                          "sales_l30": c["sls_l30"], "sales_p30": c["sls_p30"], "orders_l30": c["ord_l30"],
                          "acos_l30": a, "acos_p30": div(c["spd_p30"], c["sls_p30"]), "cvr_l30": div(c["ord_l30"], c["clk_l30"]),
                          "spend_chg": chg(c["spd_l30"], c["spd_p30"]), "share_l30": c["spd_l30"] / L["spend"] if L["spend"] else None,
                          "flags": flags})
    ct = defaultdict(lambda: defaultdict(float))
    for c in campaigns:
        if c["spend_l30"] > 0:
            ct[c["type"]]["spend"] += c["spend_l30"]
            ct[c["type"]]["_"] = 0; ct[c["type"]]["sales"] += c["sales_l30"]; ct[c["type"]]["n"] += 1
    campaign_types = sorted([{"type": k, "spend": v["spend"], "sales": v["sales"], "n": int(v["n"]),
                              "acos": div(v["spend"], v["sales"]), "share": v["spend"] / L["spend"]}
                             for k, v in ct.items() if v["spend"] >= 1], key=lambda x: -x["spend"])
    live = [c for c in campaigns if c["spend_l30"] > 0]
    camp_summary = {
        "with_spend_l30": len(live), "enabled_now": sum(1 for c in live if c["status"] == "ENABLED"),
        "paused_now_spend": sum(c["spend_l30"] for c in live if c["status"] != "ENABLED"),
        "paused_now_n": sum(1 for c in live if c["status"] != "ENABLED"),
        "acos_over_100_n": sum(1 for c in live if "ACoS > 100%" in c["flags"]),
        "acos_over_100_spend": sum(c["spend_l30"] for c in live if "ACoS > 100%" in c["flags"]),
        "no_order_n": sum(1 for c in live if "No orders" in c["flags"]),
        "no_order_spend": sum(c["spend_l30"] for c in live if "No orders" in c["flags"]),
        "top10_share": sum(c["spend_l30"] for c in live[:10]) / L["spend"] if L["spend"] else None,
        "rows_shown": min(len(live), CFG["campaign_rows"]),
        "prior_only_n": sum(1 for c in campaigns if c["spend_l30"] <= 0),
        "prior_only_spend": sum(c["spend_p30"] for c in campaigns if c["spend_l30"] <= 0),
    }

    # ------------------------------------------------ waste ----------------
    wt = {r["grain"]: r for r in wt_rows}
    waste_src = load("waste_terms.json", False) or st
    waste_terms = []
    for r in waste_src:
        if (r["orders"] or 0) == 0 and (r["clicks"] or 0) >= CFG["actionable_clicks"]:
            src = {k: r.get("cost_" + k) or 0 for k in ("auto", "broad", "phrase", "exact", "pt")}
            waste_terms.append({"term": r["term"], "spend": r["cost"], "clicks": r["clicks"], "impressions": r["impressions"],
                                "class": classify(r["term"]), "campaigns": r["campaigns"], "top_campaign": r["top_campaign"],
                                "main_source": max(src, key=src.get).upper()})
    by_cls = defaultdict(lambda: {"spend": 0.0, "n": 0}); by_src = defaultdict(float)
    for w in waste_terms:
        by_cls[w["class"]]["spend"] += w["spend"]; by_cls[w["class"]]["n"] += 1; by_src[w["main_source"]] += w["spend"]
    sp_spend = wt["term"]["spend_all"]
    zero_targets = sorted([{"campaign": r["campaignName"], "type": ("ASIN" if "asin=" in (r["target"] or "").lower() else
                                                                   {"TARGETING_EXPRESSION_PREDEFINED": "Auto", "TARGETING_EXPRESSION": "Category"}.get(r["ktype"], r["ktype"].replace("SB_", "SB ").title())),
                            "target": r["target"], "spend": r["spd"], "clicks": r["clk"], "impressions": r["imp"]}
                           for r in (load("zero_targets.json", False) or tgts) if r["ad_type"] == "SP" and (r["ord"] or 0) == 0 and ((r["clk"] or 0) >= 5 or (r["spd"] or 0) >= 5)],
                          key=lambda x: -x["spend"])
    waste = {"sp_spend_l30": sp_spend, "term_count": wt["term"]["n_all"],
             "actionable": wt["term"]["waste_actionable"] or 0, "actionable_n": wt["term"]["n_actionable"],
             "actionable_pct": (wt["term"]["waste_actionable"] or 0) / sp_spend,
             "longtail": (wt["term"]["waste_longtail"] or 0) - (wt["term"]["waste_actionable"] or 0),
             "longtail_n": wt["term"]["n_longtail"] - wt["term"]["n_actionable"],
             "longtail_pct": ((wt["term"]["waste_longtail"] or 0) - (wt["term"]["waste_actionable"] or 0)) / sp_spend,
             "converting_spend": sp_spend - (wt["term"]["waste_longtail"] or 0),
             "target_actionable": wt["target"]["waste_actionable"] or 0, "target_actionable_n": wt["target"]["n_actionable"],
             "target_count": wt["target"]["n_all"], "target_actionable_pct": (wt["target"]["waste_actionable"] or 0) / sp_spend,
             "listed_coverage": div(sum(w["spend"] for w in waste_terms), wt["term"]["waste_actionable"]),
             "by_class": dict(by_cls), "by_source": dict(by_src), "top_terms": waste_terms[:25], "top_targets": zero_targets[:20]}

    # ------------------------------------------------ harvest --------------
    targeted = {m.group(1) for r in tgts if r["ktype"] == "TARGETING_EXPRESSION"
                for m in [re.search(r'asin(?:-expanded)?="?([a-z0-9]{10})', (r["target"] or "").lower())] if m}
    harvest = []
    for r in st:
        o = r["orders"] or 0
        if o < CFG["harvest_min_orders"] or r["exact_covered"] or len(r["term"]) > CFG["max_term_len"]:
            continue
        if sum((r.get("orders_" + k) or 0) for k in ("auto", "broad", "phrase")) == 0:
            continue
        c = classify(r["term"])
        if c == "ASIN" and r["term"] in targeted:
            continue
        acos = div(r["cost"], r["sales"])
        tier = ("PRIME" if r["clicks"] >= CFG["prime_clicks"] and acos is not None and acos <= CFG["prime_acos"]
                else "STRONG" if acos is not None and acos <= CFG["strong_acos"] else "WATCH")
        harvest.append({"term": r["term"], "class": c, "spend": r["cost"], "sales": r["sales"], "orders": o, "clicks": r["clicks"],
                        "acos": acos, "cvr": div(o, r["clicks"]), "cpc": div(r["cost"], r["clicks"]),
                        "sources": [k.upper() for k in ("auto", "broad", "phrase") if (r.get("orders_" + k) or 0) > 0],
                        "tier": tier, "action": "ASIN target" if c == "ASIN" else "Exact keyword"})
    harvest.sort(key=lambda x: -x["sales"])
    sp_sales = sum(r["sales"] or 0 for r in daily if r["ad_type"] == "SP" and w0 <= r["date"] <= w1)
    tiers = defaultdict(lambda: {"n": 0, "sales": 0.0, "spend": 0.0})
    for h in harvest:
        tiers[h["tier"]]["n"] += 1; tiers[h["tier"]]["sales"] += h["sales"]; tiers[h["tier"]]["spend"] += h["spend"]
    exact = next((x for x in targeting if x["name"] == "Exact"), None)
    harvest_out = {"n": len(harvest), "sales": sum(h["sales"] for h in harvest), "spend": sum(h["spend"] for h in harvest),
                   "sales_share_of_sp": div(sum(h["sales"] for h in harvest), sp_sales), "sp_sales_l30": sp_sales,
                   "tiers": {k: dict(v) for k, v in tiers.items()}, "rows": harvest[:30],
                   "exact_spend_share": exact["share_l30"] if exact else 0, "exact_spend_share_p30": exact["share_p30"] if exact else 0,
                   "exact_sales_share": exact["sales_share_l30"] if exact else 0, "exact_acos": exact["l30"]["acos"] if exact else None,
                   "sqp": None}
    if sqp:
        exact_kw = {(r["target"] or "").lower().strip() for r in tgts if r["ktype"] == "EXACT"}
        phrase_kw = [(r["target"] or "").lower().strip() for r in tgts if r["ktype"] == "PHRASE"]
        broad_kw = [set((r["target"] or "").lower().replace("+", "").split()) for r in tgts if r["ktype"] == "BROAD"]
        paid = {r["term"]: r for r in st}
        sq = []
        for r in sqp:
            q = r["query"]
            cov = "Exact" if q in exact_kw else ("Phrase" if any(k and k in q for k in phrase_kw) else
                                                ("Broad" if any(k and k.issubset(set(q.split())) for k in broad_kw) else "None"))
            pt = paid.get(q)
            sq.append({"query": q, "class": classify(q), "volume": r["volume"], "market_purchases": r["total_purchases"],
                       "brand_purchases": r["brand_purchases"], "purchase_share": div(r["brand_purchases"], r["total_purchases"]),
                       "click_share": div(r["brand_clicks"], r["total_clicks"]), "impr_share": div(r["brand_impr"], r["total_impr"]),
                       "keyword_coverage": cov, "paid_spend_l30": pt["cost"] if pt else 0.0, "paid_orders_l30": pt["orders"] if pt else 0})
        sq.sort(key=lambda x: -(x["market_purchases"] or 0))
        gen = [x for x in sq if x["class"] != "Own brand"]
        harvest_out["sqp"] = {"window": [min(r["w0"] for r in sqp), max(r["w1"] for r in sqp)], "queries": len(sq),
                              "top_generic": gen[:CFG["sqp_rows"]],
                              "uncovered_generic_purchases": sum(x["market_purchases"] or 0 for x in gen[:50] if x["keyword_coverage"] == "None"),
                              "coverage_counts": {k: sum(1 for x in gen[:50] if x["keyword_coverage"] == k) for k in ("Exact", "Phrase", "Broad", "None")}}

    # ------------------------------------------------ products & inventory --
    names = {}
    inv_by = defaultdict(lambda: {"available": 0, "inbound": 0, "reserved": 0, "units_t30": 0, "units_t7": 0}); inv_meta = {}
    for r in (inv_rows or []):
        a = inv_by[r["asin"]]
        for k in ("available", "inbound", "reserved", "units_t30", "units_t7"):
            a[k] += r.get(k) or 0
        inv_meta.setdefault(r["asin"], r)
        names.setdefault(r["asin"], (r["name"] or "").split("|")[0].strip()[:60])
    inventory = []
    for asin, a in inv_by.items():
        m = inv_meta[asin]; wr = a["units_t30"] / 30 * 7
        sq_ = m.get("ship_in_qty")
        inventory.append({"asin": asin, "name": names.get(asin, asin), **a, "health": m["health"], "alert": m.get("alert") or "",
                          "ship_in_qty": int(sq_) if str(sq_ or "").isdigit() and int(sq_) > 0 else None,
                          "ship_in_date": m.get("ship_in_date") or "", "weeks_cover": div(a["available"] + a["inbound"], wr)})
    inventory.sort(key=lambda x: -x["units_t30"])
    inv_summary = None
    if inventory:
        sell = [i for i in inventory if i["units_t30"] > 0]
        inv_summary = {"skus_tracked": len(inventory),
                       "out_of_stock_selling": sum(1 for i in sell if i["available"] == 0),
                       "under_4_weeks": sum(1 for i in sell if i["weeks_cover"] is not None and 0 < i["weeks_cover"] < 4),
                       "available_units": sum(i["available"] for i in inventory),
                       "inbound_units": sum(i["inbound"] for i in inventory)}
    sp_asin_spend = sum((a["spd_l30"] or 0) for a in prods) or 1
    products = []
    for a in prods[:CFG["product_rows"]]:
        sc = asin_sc.get(a["asin"], {}); tL, tP = sc.get("L30", {}), sc.get("P30", {}); iv = inv_by.get(a["asin"])
        products.append({"asin": a["asin"], "name": names.get(a["asin"], ""), "spend_l30": a["spd_l30"] or 0, "spend_p30": a["spd_p30"] or 0,
                         "share": (a["spd_l30"] or 0) / sp_asin_spend, "ad_sales_l30": a["sls_l30"] or 0, "ad_sales_p30": a["sls_p30"] or 0,
                         "acos_l30": div(a["spd_l30"], a["sls_l30"]), "acos_p30": div(a["spd_p30"], a["sls_p30"]),
                         "cvr_l30": div(a["ord_l30"], a["clk_l30"]), "cvr_p30": div(a["ord_p30"], a["clk_p30"]),
                         "total_sales_l30": tL.get("sales"), "total_sales_p30": tP.get("sales"),
                         "asp_l30": div(tL.get("sales"), tL.get("units")), "asp_p30": div(tP.get("sales"), tP.get("units")),
                         "us_l30": div(tL.get("units"), tL.get("sessions")), "us_p30": div(tP.get("units"), tP.get("sessions")),
                         "available": iv["available"] if iv else None, "health": inv_meta.get(a["asin"], {}).get("health")})
    prod_summary = {"advertised_asins": len(prods), "top5_share": sum((a["spd_l30"] or 0) for a in prods[:5]) / sp_asin_spend}

    # ------------------------------------------------ budgets & Q4 ---------
    name_by_id = {c["id"]: c for c in campaigns}
    cons = []
    for b in budget["constrained"]:
        c = name_by_id.get(str(b["campaign_id"]), {})
        cons.append({**b, "campaign": c.get("name", b["campaign_id"]), "budget": c.get("budget")})
    budgets = {"window": budget["window"], "checked": budget["checked"], "constrained": cons,
               "missed_sales_lo": sum(b["missed_sales_lo"] for b in cons), "missed_sales_hi": sum(b["missed_sales_hi"] for b in cons)}
    q4 = None
    if lyq and scm:
        wk = sorted([{"wk": r["k"][:10], "total_sales": r["sales"], "units": r["units"]} for r in lyq if r["kind"] == "week"], key=lambda x: x["wk"])
        days = sorted([{"date": r["k"][:10], "total_sales": r["sales"], "units": r["units"]} for r in lyq if r["kind"] == "day"],
                      key=lambda x: -(x["total_sales"] or 0))[:5]
        qy = str(cfg.get("q4_year") or (int(cfg["report_date"][:4]) - 1))
        nd = [m for m in scm if m["mon"] in (qy + "-11", qy + "-12")]
        yr = [m for m in scm if qy + "-01" <= m["mon"] <= qy + "-12"]
        q4 = {"year": qy, "ly_weekly": wk, "ly_top_days": days, "ly_nov_dec_sales": sum(m["total_sales"] for m in nd),
              "ly_nov_dec_units": sum(m["units"] for m in nd), "ly_2025_sales": sum(m["total_sales"] for m in yr),
              "ly_nov_dec_share_of_2025": div(sum(m["total_sales"] for m in nd), sum(m["total_sales"] for m in yr)),
              "ly_2025_months": len(yr),
              "available_units_now": inv_summary["available_units"] if inv_summary else None,
              "inbound_units_now": inv_summary["inbound_units"] if inv_summary else None}

    data_notes = []
    camp_cov = div(sum(c["spend_l30"] for c in campaigns), L["spend"])
    if len(camps) >= 1000:
        data_notes.append(f"Campaign views cover the top {len(camps):,} campaigns by spend ({camp_cov*100:.1f}% of ad spend).")
    st_cov = div(sum(r["cost"] or 0 for r in st), sp_spend)
    if len(st) >= 1000:
        data_notes.append(f"Harvest candidates are scanned from the top {len(st):,} search terms by spend ({st_cov*100:.1f}% of SP spend).")
    tg_cov = div(sum(r["spd"] or 0 for r in tgts if r["ad_type"] == "SP"), sp_spend)
    if tg_cov is not None and tg_cov < 0.95:
        data_notes.append(f"Keyword coverage checks use the top {len(tgts):,} keywords and targets by spend ({tg_cov*100:.1f}% of SP spend), so coverage is understated.")
    if inv_rows and len(inv_rows) >= 300:
        data_notes.append(f"Inventory views cover the top {len(inv_rows):,} SKUs by units shipped in the last 30 days.")
    if sum(c["spend_l30"] for c in campaigns if c["type"] == "Unclassified") > 0.01 * L["spend"]:
        data_notes.append("Campaigns outside the classified set are shown as Unclassified.")

    last_by_type = {}
    for r in daily:
        if (r["cost"] or 0) > 0:
            last_by_type[r["ad_type"]] = max(last_by_type.get(r["ad_type"], ""), r["date"])
    nm_at = {"SP": "Sponsored Products", "SB": "Sponsored Brands", "SBV": "Sponsored Brands Video", "SD": "Sponsored Display"}
    stale = []
    for at, ld in sorted(last_by_type.items()):
        gap = (dt.date.fromisoformat(l1) - dt.date.fromisoformat(ld)).days
        if gap >= 4 and ld >= p0:
            stale.append({"ad_type": nm_at[at], "last_date": ld, "gap_days": gap})
            data_notes.append(f"{nm_at[at]} has no spend after {ld} ({gap} days before the end of the last 30 days).")

    # ------------------------------------------------ alert summary (data only)
    alerts = []
    def alert(level, area, tab, text):
        alerts.append({"level": level, "area": area, "tab": tab, "text": text})
    R = {r["key"]: r for r in rows}
    fm = lambda v: f"${v:,.0f}"
    if "total_sales" in R and R["total_sales"]["mom"] is not None and abs(R["total_sales"]["mom"]) >= 0.15:
        r = R["total_sales"]
        alert("high" if r["mom"] < 0 else "info", "Sales", "trends",
              f"Total sales {'down' if r['mom'] < 0 else 'up'} {abs(r['mom'])*100:.0f}% vs prior 30 days ({fm(r['l30'])} vs {fm(r['p30'])})"
              + (f"; {r['yoy']*100:+.0f}% vs last year" if r["yoy"] is not None else "") + ".")
    if R["acos"]["mom"] is not None and abs(R["acos"]["mom"]) >= 0.03:
        r = R["acos"]
        alert("high" if r["mom"] > 0 else "info", "Efficiency", "trends",
              f"ACoS {r['l30']*100:.1f}% vs {r['p30']*100:.1f}% prior 30 days ({r['mom']*100:+.1f} pts).")
    if "tacos" in R and R["tacos"]["mom"] is not None and abs(R["tacos"]["mom"]) >= 0.02:
        r = R["tacos"]
        alert("high" if r["mom"] > 0 else "info", "Efficiency", "trends",
              f"TACoS {r['l30']*100:.1f}% vs {r['p30']*100:.1f}% prior 30 days ({r['mom']*100:+.1f} pts).")
    sm, am_ = R["spend"]["mom"], R["ad_sales"]["mom"]
    if sm is not None and am_ is not None and sm > 0.05 and am_ < 0:
        alert("high", "Efficiency", "trends", f"Ad spend up {sm*100:.0f}% while ad sales fell {abs(am_)*100:.0f}% vs prior 30 days.")
    if waste["actionable_pct"] >= 0.08:
        alert("high" if waste["actionable_pct"] >= 0.12 else "watch", "Wasted spend", "wasted",
              f"{fm(waste['actionable'])} ({waste['actionable_pct']*100:.1f}% of SP spend) on {waste['actionable_n']:,} search terms with 5+ clicks and no orders (conversion-complete window).")
    if camp_summary["no_order_n"]:
        alert("watch", "Campaigns", "campaigns", f"{camp_summary['no_order_n']} campaign{'s' if camp_summary['no_order_n'] != 1 else ''} spent {fm(camp_summary['no_order_spend'])} in the last 30 days with $100+ spend and no orders.")
    if camp_summary["acos_over_100_n"]:
        alert("watch", "Campaigns", "campaigns", f"{camp_summary['acos_over_100_n']} campaign{'s' if camp_summary['acos_over_100_n'] != 1 else ''} above 100% ACoS ({fm(camp_summary['acos_over_100_spend'])} spend).")
    pr = harvest_out["tiers"].get("PRIME")
    if pr and pr["n"]:
        alert("info", "Harvest", "harvest", f"{pr['n']} PRIME search terms (30+ clicks, ACoS 40% or lower) converting outside Exact: {fm(pr['sales'])} sales.")
    if inv_summary and inv_summary["out_of_stock_selling"]:
        alert("high", "Inventory", "products", f"{inv_summary['out_of_stock_selling']} selling SKU{'s' if inv_summary['out_of_stock_selling'] != 1 else ''} out of stock at FBA.")
    if inv_summary and inv_summary["under_4_weeks"]:
        alert("watch", "Inventory", "products", f"{inv_summary['under_4_weeks']} selling SKU{'s' if inv_summary['under_4_weeks'] != 1 else ''} under 4 weeks of cover.")
    if budgets["constrained"]:
        alert("watch", "Budgets", "budgets", f"{len(budgets['constrained'])} of {budgets['checked']} campaigns checked ran out of budget; estimated missed sales {fm(budgets['missed_sales_lo'])}–{fm(budgets['missed_sales_hi'])} over 7 days.")
    for s_ in stale:
        alert("watch", "Data", "ad_spend", f"{s_['ad_type']}: no spend since {s_['last_date']}.")
    order_l = {"high": 0, "watch": 1, "info": 2}
    alerts.sort(key=lambda a: order_l[a["level"]])

    findings = {
        "meta": {"display_brand": cfg["display_brand"], "marketplace": cfg["marketplace"], "l30": cfg["l30"], "p30": cfg["p30"],
                 "ly": cfg["ly"], "lag": [w0, w1], "has_ly_ads": has_ly_ads, "stale": stale, "report_date": cfg["report_date"], "has_sc": has_sc, "notes": cfg.get("notes", []) + data_notes,
                 "ad_start_month": ad_start_month, "first_by_type": first_by_type, "brand_terms": brand_terms, "competitor_terms": comp_terms},
        "config": CFG, "alerts": alerts, "period": {"rows": rows}, "months": months, "weekly": weekly,
        "allocation": {"ad_type": ad_type, "targeting": targeting, "placements": placements},
        "strategy_mix": strategy_mix, "campaigns": campaigns, "campaign_types": campaign_types, "campaign_summary": camp_summary,
        "waste": waste, "harvest": harvest_out, "products": products, "product_summary": prod_summary,
        "inventory": inventory[:20], "inventory_summary": inv_summary, "budgets": budgets, "q4": q4,
        "reconciliation": {"campaign_table_spend_l30": sum(c["spend_l30"] for c in campaigns), "daily_spend_l30": L["spend"],
                           "search_term_sp_spend_l30": sp_spend, "strategy_spend": tot_sp,
                           "targeting_spend_l30": sum(x["l30"]["spend"] for x in targeting),
                           "campaigns_returned": len(camps), "st_rows": len(st)},
    }
    json.dump(findings, open(os.path.join(acct, "findings.json"), "w"), indent=1, default=float)
    return findings


if __name__ == "__main__":
    f = main(sys.argv[1])
    print(json.dumps(f["reconciliation"], indent=1))
    for r in f["period"]["rows"]:
        print(f'  {r["label"]:<22} {r["l30"]!s:<22} {r["p30"]!s:<22} mom={r["mom"]} yoy={r["yoy"]}')
    print("strategy", [(s["name"], round(s["spend"]), round(s["share"], 3), round(s["acos"] or 0, 3)) for s in f["strategy_mix"]])
    print("ctypes", [(c["type"], round(c["spend"]), c["n"], round(c["acos"] or 0, 3)) for c in f["campaign_types"]])
    print("camp", f["campaign_summary"])
    w = f["waste"]; print("waste", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in w.items() if not isinstance(v, (list, dict))})
    h = f["harvest"]; print("harvest", h["n"], round(h["sales"]), h["sales_share_of_sp"], h["tiers"], "exact", h["exact_spend_share"], h["exact_acos"])
    if h["sqp"]:
        print("sqp", h["sqp"]["window"], h["sqp"]["coverage_counts"])
    print("inv", f["inventory_summary"]); print("budgets", len(f["budgets"]["constrained"]), f["budgets"]["missed_sales_hi"])
    print("q4", {k: v for k, v in (f["q4"] or {}).items() if not isinstance(v, list)})
    print("ad_start", f["meta"]["ad_start_month"])
