#!/usr/bin/env python3
"""Turn raw AMC query results (the six-query pack) into the inputs amc_findings.py reads.

<folder>/raw/ holds one JSON list of row dicts per query, as returned by get_amc_query_result /
paged_query_result (cells may be strings; "" or null = below the privacy floor):
  q1.json  1_ntb_monthly         q4.json  4_repeat_sns_by_asin
  q2.json  2_ntb_search_terms    q5.json  5_path_to_conversion
  q3.json  3_repeat_sns_monthly  q6.json  6_time_to_conversion
q2 may instead be several page files q2_*.json (concatenated).

Writes ntb.json, search_terms.json, repeat.json, asin_raw.json, path_v2.json, ttc_raw.json and,
when missing, meta.json (from --brand, --year, --last-month and optional --note lines).

Usage: python3 tools/amc_ingest.py <folder> --brand "<Brand>" [--year 2026 --first-month 1 --last-month 9] [--note "..."]
"""
import argparse, calendar, glob, json, os
from datetime import date

ADS = {"sponsored_products": "SP", "sponsored_brands": "SB", "sponsored_display": "SD"}


def f(v):
    if v in (None, ""):
        return 0.0
    return float(v)


def key(v):
    return (v or "")[:7] or None


def load(d, n):
    """raw/<n> as JSON rows, or raw/<stem>.tsv (header row, tab-separated; only the columns used)."""
    p = os.path.join(d, "raw", n)
    if os.path.exists(p):
        return json.load(open(p))
    t = p[:-5] + ".tsv"
    if os.path.exists(t):
        L = [l.rstrip("\n").split("\t") for l in open(t) if l.strip()]
        return [dict(zip(L[0], r + [""] * (len(L[0]) - len(r)))) for r in L[1:]]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("--brand", required=True)
    ap.add_argument("--year", type=int, default=2026); ap.add_argument("--first-month", type=int, default=1)
    ap.add_argument("--last-month", type=int, default=9); ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--pulled", default=date.today().isoformat())
    a = ap.parse_args(); d = a.folder
    Y = a.year; ms = list(range(a.first_month, a.last_month + 1))
    keys = [f"{Y}-{m:02d}" for m in ms]; labels = [f"{calendar.month_abbr[m]} {Y}" for m in ms]
    idx = {k: i for i, k in enumerate(keys)}; n = len(keys)
    z = lambda: [0] * n

    # q1 NTB monthly
    q1 = load(d, "q1.json")
    N = {k: z() for k in ("customers", "ntb_customers", "purchases", "ntb_purchases", "sales", "ntb_sales", "spend", "sp_ntb", "sb_ntb")}
    for r in q1:
        i = idx.get(key(r["month_start"]))
        if i is None:
            continue
        if r["view_level"] == "account":
            for k in ("customers", "ntb_customers", "purchases", "ntb_purchases", "sales", "ntb_sales", "spend"):
                N[k][i] = round(f(r[k]), 2) if k in ("sales", "ntb_sales", "spend") else int(f(r[k]))
        elif r["product_type"] == "sponsored_products":
            N["sp_ntb"][i] = int(f(r["ntb_purchases"]))
        elif r["product_type"] == "sponsored_brands":
            N["sb_ntb"][i] = int(f(r["ntb_purchases"]))
    json.dump(N, open(os.path.join(d, "ntb.json"), "w"))

    # q2 search terms
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "raw", "q2*.json"))):
        j = json.load(open(p)); rows += j["rows"] if isinstance(j, dict) else j
    json.dump([{k: (r.get(k) or None) for k in ("customer_search_term", "ad_product_type", "ntb_customers", "ntb_purchases",
                                               "ntb_sales", "impressions", "clicks", "spend")} for r in rows],
              open(os.path.join(d, "search_terms.json"), "w"))

    # q3 repeat monthly
    R = {k: z() for k in ("customers", "orders", "sales", "sns_customers", "sns_sales", "repeat_customers", "repeat_sales",
                           "one_customers", "one_sales", "signups")}
    src = {"one_customers": "one_time_customers", "one_sales": "one_time_sales", "signups": "sns_signups"}
    for r in load(d, "q3.json"):
        i = idx.get(key(r["month_start"]))
        if i is None:
            continue
        for k in R:
            v = f(r.get(src.get(k, k)))
            R[k][i] = round(v, 2) if k.endswith("sales") else int(v)
    json.dump(R, open(os.path.join(d, "repeat.json"), "w"))

    # q4 by ASIN
    out = []
    for r in load(d, "q4.json"):
        if not r.get("tracked_asin"):
            continue
        out.append([r["tracked_asin"]] + [f(r.get(k)) for k in ("customers", "orders", "sales", "units", "sns_customers", "sns_orders", "sns_sales",
                                                           "repeat_customers", "repeat_orders", "repeat_sales", "one_time_customers",
                                                           "one_time_orders", "one_time_sales")])
    json.dump(out, open(os.path.join(d, "asin_raw.json"), "w"))

    # q5 path
    P = []
    for r in load(d, "q5.json"):
        m = key(r["month_start"])
        if m and m not in idx:
            continue
        P.append({"month": m, "path": r["path"] or "(below privacy floor)", "buyers": int(f(r["buyers"])), "orders": int(f(r["orders"])),
                  "sales": round(f(r["sales"]), 2), "avg_touch_days": f(r["avg_touch_days"]),
                  "avg_days_to_order": f(r["avg_days_first_touch_to_order"]), "buyers_clicked": int(f(r["buyers_who_clicked"]))})
    P = [p for p in P if p["month"] is None or p["path"] != "(below privacy floor)"] + \
        [dict(p, month=None) for p in P if p["month"] and p["path"] == "(below privacy floor)"]
    json.dump(P, open(os.path.join(d, "path_v2.json"), "w"))

    # q6 time to conversion
    T = [[ADS.get(r["ad_product_type"] or "", "-"), int(f(r["ttc_bucket"])), int(f(r["purchases"])), int(f(r["ntb_purchases"])),
          round(f(r["sales"]), 2)] for r in load(d, "q6.json") if r.get("ttc_bucket") not in (None, "")]
    json.dump(T, open(os.path.join(d, "ttc_raw.json"), "w"))

    mp = os.path.join(d, "meta.json")
    if not os.path.exists(mp):
        pm = date(Y, a.first_month, 1); lb3 = date(Y - 1 if a.first_month <= 3 else Y, (a.first_month - 4) % 12 + 1, 1)
        lb1 = date(Y - 1 if a.first_month == 1 else Y, (a.first_month - 2) % 12 + 1, 1)
        last = date(Y, a.last_month, calendar.monthrange(Y, a.last_month)[1])
        fmt = lambda x: f"{calendar.month_abbr[x.month]} {x.day}, {x.year}"
        win = f"{calendar.month_abbr[pm.month]} 1 – {calendar.month_abbr[last.month]} {last.day}, {Y}"
        pulled = date.fromisoformat(a.pulled)
        has_sns = sum(R["signups"]) + sum(R["sns_sales"]) > 0
        notes = ["AMC sees mostly shoppers reached by Sponsored Ads; rates and trends are reliable, raw counts are understated.",
                 "Sponsored Ads only: DSP touches and DSP-attributed sales are not included.",
                 "Rows under ~100 shoppers are withheld by AMC. They stay in totals and are never attributed.",
                 ("Subscribe & Save: a customer counts as SnS from the month of their first sign-up."
                  if has_sns else f"No Subscribe & Save activity in the window; repeat = bought earlier (from {calendar.month_abbr[lb3.month]} {lb3.year}) or 2+ orders in the month."),
                 "Repeat history starts at the lookback date, so early months have a shorter purchase history than later months; part of the rise in repeat share over the year comes from that longer window.",
                 "Spend per NTB order uses all Sponsored Ads spend and ranks months; it is not an isolated acquisition cost."] + a.note
        meta = {"brand": a.brand, "marketplace": "US", "pulled": a.pulled,
                "period": f"{calendar.month_abbr[pm.month]} – {calendar.month_abbr[last.month]} {Y}",
                "months": labels, "month_keys": keys, "window_label": win,
                "repeat_window": f"{calendar.month_abbr[pm.month]} – {calendar.month_abbr[last.month]} {Y}",
                "windows": [["Reporting window", f"{win} (complete months)"], ["Repeat lookback", f"from {fmt(lb3)}"],
                            ["Path to conversion lookback", f"30 days before each buyer's first order of the month (from {fmt(lb1)})"],
                            ["Attribution", "purchases attribute for 14 days after the ad interaction"], ["Data pulled", fmt(pulled)]],
                "notes": notes}
        json.dump(meta, open(mp, "w"), indent=1)
    print("[done]", d, "months", keys[0], "-", keys[-1], "| q2 rows", len(rows), "| asins", len(out), "| path rows", len(P))


if __name__ == "__main__":
    main()
