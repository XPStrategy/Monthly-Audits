#!/usr/bin/env python3
"""Weekly refresh of hub/performance.html without re-pulling history.

The page already holds 24 weeks / 24 months per account. Each Tuesday only these periods change:
  - the last two full weeks (Sun-Sat): the latest is new, the one before may still move (Vendor Central, late ad sales)
  - the last full month and the month before
  - month to date (1st of the month through --mtd-end) and the same days of the month before
Everything else is read back from the current page and kept as is.

Sources
  Ad Spend / Ad Sales: the XP PC's Amazon Ads API pull, history\\ads_daily.json (pc/xp_performance/ads_pull.py).
      A period is taken from the PC only when every day of it is in that file; otherwise the page keeps its value.
  Total Sales: MerchantSpring getSalesByChannels, three calls for all stores (USD, ex tax, Vendor = orderedRevenue):
      ch_week.json (cur = last week, prior = week before), ch_month.json (cur = last full month, prior = month before),
      ch_mtd.json (cur = month to date, prior = same days of the month before). Saved as returned ({"rows": [...]}).
  Accounts the PC pull does not cover (no Ads API profile, partial coverage, or not USD) get sales AND ads from
      getSalesByPeriod per store, three small calls each: <channelId>_W.json (interval w, the two weeks),
      <channelId>_M.json (interval M, the two months), <channelId>_MTD.json (interval M over month to date, custom prior).
      Saved as {"currency", "rows": [{startTime, endTime, sales, priorSales, adSpend, priorAdSpend, adSales, priorAdSales}]}.
  Badass Moto (not in MerchantSpring): MAP files in --raw, same format as build_performance.py, g W / M / D.

    python3 tools/refresh_performance.py --repo . --plan --ads <ads_daily.json> --data-end 2026-11-28 --mtd-end 2026-11-30
    python3 tools/refresh_performance.py --repo . --ads <ads_daily.json> --ms <folder> [--raw <folder>] --data-end ... --mtd-end ...

--plan prints the date windows and the stores that need getSalesByPeriod calls. Without --plan the page is rebuilt and
checked; exit 0 = commit hub/performance.html and hub/index.html, exit 1 = do not publish (reasons printed).
"""
import argparse, calendar, json, os, re, sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_master as M         # noqa: E402
import build_performance as BP   # noqa: E402

PARTIAL_PC = {"altun"}   # PC has only one of Altun's four brands (Zesty Snackz): use MerchantSpring for its ads
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def windows(data_end, mtd_end):
    wk = data_end - timedelta(days=6)
    nxt = mtd_end + timedelta(days=1)
    lm_end = nxt.replace(day=1) - timedelta(days=1)                      # last full month
    pm_end = lm_end.replace(day=1) - timedelta(days=1)
    m_start = mtd_end.replace(day=1)
    p_end_month = m_start - timedelta(days=1)
    p_end = p_end_month.replace(day=min(mtd_end.day, p_end_month.day))
    return {
        "week": {"cur": [wk, data_end], "prior": [wk - timedelta(days=7), wk - timedelta(days=1)]},
        "month": {"cur": [lm_end.replace(day=1), lm_end], "prior": [pm_end.replace(day=1), pm_end]},
        "mtd": {"cur": [m_start, mtd_end], "prior": [p_end.replace(day=1), p_end]},
    }


def page_data(repo):
    h = open(os.path.join(repo, "hub", "performance.html"), encoding="utf-8").read()
    i = h.index("window.PERF = ") + len("window.PERF = ")
    return json.loads(h[i:h.index(";</script>", i)])


def stores():
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "performance_stores.json")))
    return {s["channelId"]: s for s in d["stores"]}


def pc_days(path):
    """-> {client: {iso date: (spend, ad sales)}}"""
    if not path:
        return {}
    h = json.load(open(path, encoding="utf-8"))
    return {c: {d: (v.get("sp") or 0.0, v.get("asl") or 0.0) for d, v in a.get("days", {}).items()}
            for c, a in h.get("accounts", {}).items()}


def pc_sum(days, a, b):
    """Spend and ad sales over [a, b] if every day is in the PC file, else None."""
    n = (b - a).days + 1
    ks = [(a + timedelta(days=i)).isoformat() for i in range(n)]
    if not days or any(k not in days for k in ks):
        return None
    return round(sum(days[k][0] for k in ks), 2), round(sum(days[k][1] for k in ks), 2)


def ms_clients(rows):
    return {r["client"] for r in rows if r.get("src") == "MerchantSpring"}


def period_clients(rows, pc):
    """MerchantSpring accounts whose ads cannot come from the PC: no PC data, partial coverage, or not USD."""
    out = set()
    for r in rows:
        if r.get("src") != "MerchantSpring":
            continue
        if r["client"] not in pc or r["client"] in PARTIAL_PC or r["cur"] != "$":
            out.add(r["client"])
    return out


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_channels(msdir):
    """ch_<name>.json -> {name: {storeId: (cur sales, prior sales, currency)}}"""
    out = {}
    for name in ("week", "month", "mtd"):
        f = os.path.join(msdir, f"ch_{name}.json")
        if not os.path.exists(f):
            continue
        d = json.load(open(f, encoding="utf-8"))
        if isinstance(d, list) and d and isinstance(d[0], dict) and "text" in d[0]:   # saved tool result wrapper
            d = json.loads(d[0]["text"])
        out[name] = {str(x["storeId"]): (num(x["sales"]["value"]), num(x["sales"]["priorPeriodValue"]), x.get("currency"))
                     for x in d["rows"]}
    return out


def load_period(msdir, ch):
    """<ch>_W/_M/_MTD.json -> {"W": {sunday iso: {cur...}}, "M": {yyyy-mm: ...}, "MTD": {"cur": ..., "prior": ...}}"""
    out = {}
    for g in ("W", "M", "MTD"):
        f = os.path.join(msdir, f"{ch}_{g}.json")
        if not os.path.exists(f):
            continue
        d = json.load(open(f, encoding="utf-8"))
        rows = d["rows"]
        def vals(r, pre):   # pre "" = current period, "p" = prior period
            f = (lambda n: r.get(n)) if pre == "" else (lambda n: r.get("prior" + n[0].upper() + n[1:]))
            return {"ts": num(f("sales")), "sp": num(f("adSpend")), "asl": num(f("adSales"))}
        if g == "MTD":
            tot = {"cur": defaultdict(float), "prior": defaultdict(float)}
            for r in rows:
                for key, pre in (("cur", ""), ("prior", "p")):
                    for k, v in vals(r, pre).items():
                        tot[key][k] += v
            out["MTD"] = {k: dict(v) for k, v in tot.items()}
            continue
        o = out.setdefault(g, {})
        for r in rows:
            st = r["startTime"]
            if g == "W":
                dd, mm, yy = map(int, st.split("/")); k = date(yy, mm, dd).isoformat()
            elif "/" in st:
                dd, mm, yy = map(int, st.split("/")); k = f"{yy}-{mm:02d}"
            else:
                mo, yy = st.split(); k = f"{yy}-{MON[mo[:3]]:02d}"
            o[k] = vals(r, "")
    return out


def cell(k, ts, sp, asl):
    ts = round(ts, 2) if ts else None
    return {"k": k, "ts": ts, "sp": sp, "asl": asl,
            "acos": (sp / asl) if sp is not None and asl else None,
            "tacos": (sp / ts) if sp is not None and ts else None, "pa": False, "pt": False}


def upsert(lst, new):
    for i, x in enumerate(lst):
        if x["k"] == new["k"]:
            lst[i] = new
            return
    lst.append(new)
    lst.sort(key=lambda x: x["k"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ads", help="PC history\\ads_daily.json")
    ap.add_argument("--ms", help="folder with ch_*.json and <channelId>_W/_M/_MTD.json")
    ap.add_argument("--raw", help="MAP folder for Badass Moto (optional)")
    ap.add_argument("--data-end", required=True, help="last Saturday, yyyy-mm-dd")
    ap.add_argument("--mtd-end", required=True, help="yesterday, yyyy-mm-dd")
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    data_end, mtd_end = date.fromisoformat(a.data_end), date.fromisoformat(a.mtd_end)
    if data_end.weekday() != 5:
        sys.exit("--data-end must be a Saturday")
    W = windows(data_end, mtd_end)
    P = page_data(a.repo)
    rows = P["rows"]
    pc = pc_days(a.ads)
    per = period_clients(rows, pc)
    S = stores()

    if a.plan:
        iso = lambda p: {k: [x.isoformat() for x in v] for k, v in p.items()}
        need = [dict(S[ch], client=cl) for ch, cl in BP.MS_CHANNELS.items() if cl in per and ch in S]
        cover = {c: (min(d), max(d), len(d)) for c, d in pc.items() if d}
        print(json.dumps({"windows": {k: iso(v) for k, v in W.items()}, "period_stores": need,
                          "pc_clients": sorted(pc), "pc_coverage": cover}, indent=1, default=str))
        return

    ch = load_channels(a.ms) if a.ms else {}
    fails, notes, changes = [], [], []
    by_client_stores = defaultdict(list)
    for c_, cl in BP.MS_CHANNELS.items():
        by_client_stores[cl].append(c_)

    # Badass Moto / other MAP rows
    acc, meta = BP.load(a.raw) if a.raw and os.path.isdir(a.raw) else ({}, {})

    wk, wkp = W["week"]["cur"][0].isoformat(), W["week"]["prior"][0].isoformat()
    lm, pm = W["month"]["cur"][0].strftime("%Y-%m"), W["month"]["prior"][0].strftime("%Y-%m")
    periods = [("W", wk, "week", "cur"), ("W", wkp, "week", "prior"), ("M", lm, "month", "cur"),
               ("M", pm, "month", "prior"), ("MTD", "cur", "mtd", "cur"), ("MTD", "prior", "mtd", "prior")]

    for r in rows:
        s = r.get("s")
        if not s:
            continue
        s.setdefault("MTD", {})
        client, src = r["client"], r.get("src")
        old = {("W", x["k"]): x for x in s["W"]}
        old.update({("M", x["k"]): x for x in s["M"]})
        old.update({("MTD", k): v for k, v in (s.get("MTD") or {}).items() if v})

        for g, key, win, side in periods:
            a_, b_ = W[win][side]
            prev = old.get((g, key))
            k_out = key if g != "MTD" else ("MTD" if key == "cur" else "MTD-prior")
            ts = sp = asl = None
            if src == "Marketplace Ad Pros":
                rk = r["id"]
                if rk not in acc:
                    continue
                c = acc[rk]["D" if g == "MTD" else g].get(key)
                if not c:
                    continue
                days = (b_ - a_).days + 1
                ts = c["ts"] if c.get("nd_ts", 0) >= days else (prev or {}).get("ts")
                if c.get("nd_ad", 0) >= days:
                    sp, asl = round(c["sp"], 2), round(c["asl"], 2)
                else:
                    sp, asl = (prev or {}).get("sp"), (prev or {}).get("asl")
            elif client in per:
                agg = defaultdict(float); got = False
                for c_ in by_client_stores[client]:
                    if not os.path.exists(os.path.join(a.ms or "", f"{c_}_{'MTD' if g == 'MTD' else g}.json")):
                        continue
                    d = load_period(a.ms, c_)
                    v = (d.get("MTD") or {}).get(key) if g == "MTD" else (d.get(g) or {}).get(key)
                    if v:
                        got = True
                        for k, x in v.items():
                            agg[k] += x
                if not got:
                    if g == "W" and key == wk:
                        fails.append(f"{r['brand']}: no MerchantSpring period file for week {wk}")
                    continue
                ts, sp, asl = agg["ts"], round(agg["sp"], 2), round(agg["asl"], 2)
            else:
                cs = ch.get(win)
                if cs is None:
                    fails.append(f"ch_{win}.json missing")
                    continue
                vals = [cs[c_] for c_ in by_client_stores[client] if c_ in cs]
                if not vals:
                    if g == "W" and key == wk:
                        fails.append(f"{r['brand']}: no store in ch_{win}.json")
                    continue
                ts = sum(v[0] if side == "cur" else v[1] for v in vals)
                pcv = pc_sum(pc.get(client), a_, b_)
                if pcv:
                    sp, asl = pcv
                    if prev and prev.get("sp"):
                        dif = (sp - prev["sp"]) / prev["sp"]
                        if abs(dif) > 0.02:
                            notes.append(f"{r['brand']} {k_out}: PC ad spend {sp:,.2f} vs page {prev['sp']:,.2f} ({dif:+.1%})")
                else:
                    sp, asl = (prev or {}).get("sp"), (prev or {}).get("asl")
                    if prev is None or prev.get("sp") is None:
                        notes.append(f"{r['brand']} {k_out}: PC ads do not cover {a_}..{b_}; ad columns left empty")
            new = cell(k_out, ts, sp, asl)
            if g == "MTD":
                s["MTD"][key] = new
            else:
                upsert(s[g], new)
            changes.append((r["brand"], k_out))
        s["W"], s["M"] = s["W"][-25:], s["M"][-25:]
        s["Y"] = BP.annual(s["M"])
        if not s["MTD"]:
            s.pop("MTD")

    # refresh AM / PPC / status from the team file
    M.build(a.repo) if hasattr(M, "build") else None
    hubs = {re.sub(r"-[0-9a-f]{8}$", "", h["slug"]): h for h in M.rows(a.repo)}
    for r in rows:
        h = hubs.get(r["client"])
        if h:
            r.update(am=h["am"], ppc=h["ppc"], status=h["status"], note=h["note"])

    # checks
    for r in rows:
        if not r.get("s") or r.get("src") not in ("MerchantSpring", "Marketplace Ad Pros"):
            continue
        s = r["s"]
        if not s["W"] or s["W"][-1]["k"] != wk or s["W"][-1]["ts"] is None:
            fails.append(f"{r['brand']}: latest week {s['W'][-1]['k'] if s['W'] else None} (expected {wk}) or no sales")
        if r.get("src") == "MerchantSpring":
            if not any(x["k"] == lm and x["ts"] is not None for x in s["M"]):
                fails.append(f"{r['brand']}: no {lm} sales")
            if not s.get("MTD") or s["MTD"].get("cur", {}).get("ts") is None:
                fails.append(f"{r['brand']}: no month-to-date sales")
            if r["client"] in pc and r["client"] not in per and s["W"] and s["W"][-1]["sp"] is None:
                fails.append(f"{r['brand']}: no ad spend for week {wk} (PC file incomplete?)")

    mtd = {"start": W["mtd"]["cur"][0].isoformat(), "end": mtd_end.isoformat(),
           "pstart": W["mtd"]["prior"][0].isoformat(), "pend": W["mtd"]["prior"][1].isoformat()}
    p = os.path.join(a.repo, "hub", "performance.html")
    open(p, "w", encoding="utf-8").write(BP.page(rows, data_end, date.today().isoformat(), mtd))
    print(f"[done] {p}: weeks {wkp} and {wk}, months {pm} and {lm}, month to date {mtd['start']}..{mtd['end']}; "
          f"{len({c[0] for c in changes})} accounts updated; ads from the PC for {len([c for c in pc if c not in per])} accounts, "
          f"MerchantSpring period calls for {len(per)}")
    for x in notes:
        print("NOTE:", x)
    if fails:
        print("DO NOT PUBLISH:")
        for x in sorted(set(fails)):
            print("  -", x)
        sys.exit(1)
    print(f"OK to publish: commit hub/performance.html and hub/index.html as "
          f"\"Performance Overview: weekly refresh through {data_end} (MTD through {mtd_end})\"")


if __name__ == "__main__":
    main()
