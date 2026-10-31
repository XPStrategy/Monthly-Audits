#!/usr/bin/env python3
"""Assemble amc_findings.json for one account from the saved AMC query results.

Input folder (one per account, one per run):
  meta.json          brand, marketplace, months (labels), window, pulled, notes
  ntb.json           monthly arrays: customers, ntb_customers, purchases, ntb_purchases, sales, ntb_sales, spend, sp_ntb, sb_ntb
  search_terms.json  raw AMC rows: customer_search_term, ad_product_type, ntb_customers, ntb_purchases, ntb_sales, impressions, clicks, spend
  repeat.json        monthly arrays: customers, orders, sales, sns_*, repeat_*, one_*, signups
  asin_raw.json      [asin, customers, orders, sales, units, snsC, snsO, snsS, repC, repO, repS, oneC, oneO, oneS]
  names.json         {asin: product name}
  path_v2.json       rows: month (YYYY-MM or null = suppressed), path, buyers, orders, sales, avg_touch_days, avg_days_to_order, buyers_clicked
  ttc_raw.json       [ad (SP/SB/SD/-), bucket 1-5, purchases, ntb, sales]
  brand_terms.json   regex fragments that mark a search term as branded

Usage: python3 tools/amc_findings.py <folder>   -> <folder>/amc_findings.json
"""
import json, os, re, sys

LAB = {"sponsored_products": "SP", "sponsored_brands": "SB", "sponsored_display": "SD"}
BUCKETS = {1: "Within 1 hour", 2: "1-24 hours", 3: "1-3 days", 4: "4-7 days", 5: "8-14 days"}
ADF = {"SP": "sponsored_products", "SB": "sponsored_brands", "SD": "sponsored_display"}


def path_label(p):
    return " + ".join(LAB.get(x.strip(), x.strip()) for x in p.split("+")) + (" only" if "+" not in p else "")


def load(d, n, default=None):
    p = os.path.join(d, n)
    return json.load(open(p)) if os.path.exists(p) else default


def pct(v):
    return f"{v*100:.1f}%" if v is not None else "—"


def main(d):
    meta = load(d, "meta.json"); months = meta["months"]; keys = meta["month_keys"]
    out = {"meta": meta, "months": months, "notes": meta.get("notes", []),
           "repeat_window": meta["repeat_window"], "ttc_window": meta["window_label"]}

    out["ntb"] = load(d, "ntb.json")

    # search terms
    rx = re.compile("|".join(load(d, "brand_terms.json")), re.I)
    comp = load(d, "competitor_terms.json", [])
    crx = re.compile("|".join(comp), re.I) if comp else None
    rows = load(d, "search_terms.json")
    cls = {}
    sup = {"ntb": 0, "ntb_sales": 0.0, "spend": 0.0, "clicks": 0}
    named = []
    for r in rows:
        t = r["customer_search_term"]
        v = {k: float(r[k] or 0) for k in ("ntb_purchases", "ntb_sales", "spend", "clicks")}
        if not t:
            sup["ntb"] += v["ntb_purchases"]; sup["ntb_sales"] += v["ntb_sales"]; sup["spend"] += v["spend"]; sup["clicks"] += v["clicks"]
            continue
        c = ("Long tail" if t == "zz_long_tail" else "ASIN target" if re.fullmatch(r"b0[a-z0-9]{8}", t.lower()) else "Branded" if rx.search(t)
             else "Competitor" if crx and crx.search(t) else "Generic")
        a = cls.setdefault(c, {"name": c, "ntb": 0, "ntb_sales": 0.0, "spend": 0.0, "clicks": 0})
        a["ntb"] += v["ntb_purchases"]; a["ntb_sales"] += v["ntb_sales"]; a["spend"] += v["spend"]; a["clicks"] += v["clicks"]
        if c == "Long tail":
            continue
        named.append({"term": t, "ad": r["ad_product_type"], "class": c, "ntb": v["ntb_purchases"], "ntb_sales": v["ntb_sales"],
                      "clicks": v["clicks"], "spend": v["spend"]})
    named.sort(key=lambda x: (-x["ntb"], -x["spend"]))
    out["search_terms"] = {"window": meta["window_label"],
                           "classes": [cls[k] for k in ("Branded", "Generic", "Competitor", "ASIN target", "Long tail") if k in cls],
                           "suppressed": sup, "top": named[:30], "named_count": len(named)}

    out["repeat"] = load(d, "repeat.json")
    names = load(d, "names.json", {})
    out["asin"] = [{"asin": a[0], "name": names.get(a[0], ""), "customers": a[1], "orders": a[2], "sales": a[3],
                    "sns_sales": a[7], "repeat_sales": a[10], "one_sales": a[13]} for a in load(d, "asin_raw.json")]
    out["asin"].sort(key=lambda a: -a["sales"])

    # path v2
    pr = load(d, "path_v2.json")
    paths = {}
    for r in pr:
        if not r["month"]:
            continue
        lab = path_label(r["path"])
        p = paths.setdefault(lab, {k: [None] * len(keys) for k in ("buyers", "sales", "touch_days", "days_to_order", "clicked")})
        i = keys.index(r["month"])
        p["buyers"][i] = r["buyers"]; p["sales"][i] = r["sales"]; p["touch_days"][i] = r["avg_touch_days"]
        p["days_to_order"][i] = r["avg_days_to_order"]; p["clicked"][i] = r["buyers_clicked"]
    for p in paths.values():
        p["clicked"] = [v or 0 for v in p["clicked"]]
    order = sorted(paths, key=lambda k: -sum(v or 0 for v in paths[k]["buyers"]))
    tot = sum(sum(v or 0 for v in paths[k]["buyers"]) for k in order)
    wavg = lambda key: sum(sum((paths[k][key][i] or 0) * (paths[k]["buyers"][i] or 0) for i in range(len(keys))) for k in order) / (tot or 1)
    out["path"] = {"paths": paths, "order": order, "total_touched": tot,
                   "suppressed": sum(r["buyers"] for r in pr if not r["month"]),
                   "avg_touch_days": wavg("touch_days"), "avg_days": wavg("days_to_order")}

    out["ttc"] = [{"ad": ADF[x[0]], "bucket": BUCKETS[x[1]], "purchases": x[2], "ntb": x[3], "sales": x[4]}
                  for x in load(d, "ttc_raw.json") if x[0] in ADF]

    # overview highlights (data only)
    N, Rp = out["ntb"], out["repeat"]; L = months
    cpa = [s / n if n else None for s, n in zip(N["spend"], N["ntb_purchases"])]
    ntbsh = [a / b if b else None for a, b in zip(N["ntb_purchases"], N["purchases"])]
    br = cls.get("Branded"); gtot = sum(c["ntb"] for c in cls.values()) + sup["ntb"]
    sns = [a / b if b else None for a, b in zip(Rp["sns_sales"], Rp["sales"])]
    multi = lambda i: sum((paths[k]["buyers"][i] or 0) for k in order if "+" in k) / (sum((paths[k]["buyers"][i] or 0) for k in order) or 1)
    sp_ttc = [t for t in out["ttc"] if t["ad"] == "sponsored_products"]
    sp_1h = sum(t["purchases"] for t in sp_ttc if t["bucket"] == "Within 1 hour") / (sum(t["purchases"] for t in sp_ttc) or 1)
    hi = max(range(len(L)), key=lambda i: N["ntb_purchases"][i])
    out["highlights"] = [
        f"NTB orders peaked in {L[hi]} at {N['ntb_purchases'][hi]:,}; {L[-1]} closed at {N['ntb_purchases'][-1]:,}. "
        f"NTB share of ad orders: {pct(ntbsh[0])} in {L[0]} → {pct(ntbsh[-1])} in {L[-1]}.",
        f"Spend per NTB order: ${cpa[0]:,.0f} in {L[0]} → ${cpa[-1]:,.0f} in {L[-1]}.",
        (f"Branded searches brought {pct(br['ntb'] / gtot)} of NTB orders at ${br['spend'] / br['ntb']:,.0f} per NTB order." if br and br["ntb"] else ""),
        (f"SnS share of sales: {pct(sns[0])} in {L[0]} → {pct(sns[-1])} in {L[-1]}; SnS sign-ups {Rp['signups'][0] or 0:,} → {Rp['signups'][-1] or 0:,} per month." if sum(Rp["signups"]) else f"Repeat buyers: {pct(Rp['repeat_sales'][0] / Rp['sales'][0])} of sales in {L[0]} → {pct(Rp['repeat_sales'][-1] / Rp['sales'][-1])} in {L[-1]}; no Subscribe & Save activity."),
        (f"Buyers who saw more than one ad type before buying: {pct(multi(0))} in {L[0]} → {pct(multi(len(L) - 1))} in {L[-1]}."
         if any("+" in k for k in order) else "Every ad-exposed buyer saw Sponsored Products only (no Sponsored Brands or Display activity)."),
        f"{pct(sp_1h)} of click-attributed Sponsored Products purchases happen within 1 hour of the click.",
    ]
    out["highlights"] = [h for h in out["highlights"] if h]
    json.dump(out, open(os.path.join(d, "amc_findings.json"), "w"), indent=1)
    print("[done]", os.path.join(d, "amc_findings.json"))


if __name__ == "__main__":
    main(sys.argv[1])
