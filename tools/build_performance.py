#!/usr/bin/env python3
"""Build the Performance Overview page (hub/performance.html): every hub account's last full month vs
the month before for Total Sales, Ad Spend, Ad Sales, ACoS and TACoS. Click an account to open its
Weekly / Monthly / Annual table (same layout as the Performance Overview Tracker sheet).

Data: Marketplace Ad Pros (MAP) MCP, US marketplace (UK for Badass Moto Europe), pulled with
run_report_sql into a folder of JSON results (raw MAP data stays in Drive, not in this repo):

    ads_*.json  g, b (brand), c (currency), k (yyyy-mm | week-start Sunday), sp (spend), asl (ad sales), nd (days)
                SP + SB + SD campaigns: spend = cost, ad sales = sales14d (SP) / sales (SB, SD)
    sp_*.json   g, b, c, k, ts (orderedProductSales_amount, sp_sales_traffic), nd
    vc*.json    g, b, c, k, ts (orderedRevenue, else shippedRevenue, sp_vendor_sales), nd

    python3 tools/build_performance.py --repo . --raw <folder> --data-end 2026-11-14

Month to date (the first view on the page): <channelId>_MTD.json, getSalesByPeriod / getVendorSalesByPeriod with
interval "d" from the 1st of the month to --mtd-end (usually yesterday), custom prior = the same days of the month
before; rows summed per account. MAP accounts: rows with g "D" and k "cur" / "prior" in ads_mtd.json / sp_mtd.json.

Total Sales = Seller Central ordered product sales + Vendor Central ordered revenue.
ACoS = Ad Spend / Ad Sales. TACoS = Ad Spend / Total Sales. % = change vs the period before (relative),
the same way the tracker sheet shows it. Only complete weeks (Sun-Sat) and months are shown.
"""
import argparse, calendar, glob, json, os, re, sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_monthly as P  # noqa: E402
import build_master as M     # noqa: E402

B, H, esc = P.B, P.H, P.esc

# MAP brand -> (hub client slug, row label, currency). Brands not listed are not hub accounts (skipped).
BRANDS = {
    "Advanced Bionutritionals, LLC": ("advanced-bionutritionals", None, "USD"),
    "Badass Moto": ("badass-moto", None, "USD"),
    "Badass Moto Europe": ("badass-moto", "Badass Moto Europe (UK)", "GBP"),
    "BingO": ("bingo1525", None, "USD"),
    "Cosmo Technologies": ("cosmo-technologies", None, "USD"),
    "DEZINE Group": ("dzg-products", None, "USD"),
    "Displate": ("displate", None, "USD"),
    "Inglesina USA": ("inglesina", None, "USD"),
    "Joe's Trends": ("joes-trend", None, "USD"),
    "Kensington Valley Trading": ("kensingtonvalleytrading", None, "USD"),
    "Kitchen Globe": ("boroux", None, "USD"),          # Boroux's MAP brand (Oct 2026 spend $6,419.45 matches MerchantSpring "Boroux")
    "Leading Choice Products": ("leading-choice-products", None, "USD"),
    "M-D Building Products": ("md-buildingproducts", None, "USD"),
    "Reliable Home Products": ("md-buildingproducts", None, "USD"),   # same account as M-D (tracker: "MD Building Products | Reliable Home Products")
    "Nutrivein": ("nutrivein", None, "USD"),
    "SavonGoods": ("savongoods", None, "USD"),
    "Shine Water": ("shinewater", None, "USD"),
    "SkySail Consumer": ("skysailconsumer", None, "USD"),
    "Smart Cookie Solutions Inc.": ("smart-cookie", None, "USD"),
    "Southern Dental and Medical Supplies": ("southerndental", None, "USD"),
    "Spring Mount Supply": ("spring-mount-supply", None, "USD"),
    "STEAM CLIP": ("steam-clip", None, "USD"),
    "TrailHeads Apparel USA": ("trailheads-apparel", None, "USD"),
    "TurmSkin": ("turmskin", None, "USD"),
    "Ultimate footwear": ("ultimate-footwear", None, "USD"),
    "Ultimate Washer®": ("ultimate-washer", None, "USD"),
    "VersaGroup": ("versa-group", None, "USD"),
}
SYM = {"USD": "$", "GBP": "£"}


def load(raw):
    """-> {row_key: {"W"|"M": {k: {ts, sp, asl, nd_ad, nd_ts, vc}}}}"""
    acc = defaultdict(lambda: {g: defaultdict(lambda: defaultdict(float)) for g in ("W", "M", "D")})
    meta = {}
    for f in sorted(glob.glob(os.path.join(raw, "*.json"))):
        kind = os.path.basename(f).split("_")[0].split(".")[0]
        for r in json.load(open(f))["data"]:
            m = BRANDS.get(r["b"])
            if not m or r["c"] != m[2]:
                continue
            slug, label, cur = m
            key = slug + ("|" + label if label else "")
            meta[key] = (slug, label, cur)
            cell = acc[key][r["g"]][r["k"]]
            if kind == "ads":
                cell["sp"] += r["sp"] or 0; cell["asl"] += r["asl"] or 0
                cell["nd_ad"] = max(cell["nd_ad"], r["nd"])
            else:
                cell["ts"] += r["ts"] or 0
                cell["nd_ts"] = max(cell["nd_ts"], r["nd"])
                if kind == "vc":
                    cell["vc"] += r["ts"] or 0
    return acc, meta


def mtd_days(mtd):
    return (date.fromisoformat(mtd["end"]) - date.fromisoformat(mtd["start"])).days + 1 if mtd else 0


def month_days(k):
    y, m = map(int, k.split("-"))
    return calendar.monthrange(y, m)[1]


def row(k, c, days):
    """One period: values + coverage flags. Missing source -> None."""
    has_ts = c.get("nd_ts", 0) > 0
    has_ad = c.get("nd_ad", 0) > 0
    ts = round(c["ts"], 2) if has_ts else None
    sp = round(c["sp"], 2) if has_ad else None
    asl = round(c["asl"], 2) if has_ad else None
    return {"k": k, "ts": ts, "sp": sp, "asl": asl,
            "acos": (sp / asl) if sp is not None and asl else None,
            "tacos": (sp / ts) if sp is not None and ts else None,
            "pa": bool(has_ad and c["nd_ad"] < days),     # ads only part of the period (MAP ads history starts Jan 2026)
            "pt": bool(has_ts and c["nd_ts"] < days)}


def series(acc_key, data_end, mtd=None):
    a = acc_key
    last_week = data_end - timedelta(days=(data_end.weekday() + 1) % 7)       # Sunday of data_end's week
    if data_end.weekday() != 5:                                               # data_end not a Saturday -> that week is partial
        last_week -= timedelta(days=7)
    W = [row(k, a["W"][k], 7) for k in sorted(a["W"]) if date.fromisoformat(k) <= last_week]
    last_month = (data_end.replace(day=1) - timedelta(days=1)).strftime("%Y-%m") if data_end.day < month_days(data_end.strftime("%Y-%m")) else data_end.strftime("%Y-%m")
    Mo = [row(k, a["M"][k], month_days(k)) for k in sorted(a["M"]) if k <= last_month]
    # Annual from complete months; the current year covers the months up to last_month,
    # compared with the same months of the year before.
    years = sorted({k[:4] for k in a["M"] if k <= last_month})
    Y = []
    for y in years:
        ms = [k for k in sorted(a["M"]) if k[:4] == y and k <= last_month]
        tot = defaultdict(float)
        for k in ms:
            for f in ("ts", "sp", "asl", "nd_ad", "nd_ts"):
                tot[f] += a["M"][k].get(f, 0)
        days = sum(month_days(k) for k in ms)
        r = row(y, tot, days)
        r["months"] = [ms[0], ms[-1]] if ms else None
        r["full"] = len(ms) == 12
        Y.append(r)
    # same-period comparison for the YTD row
    cur = last_month[:4]
    if Y and Y[-1]["k"] == cur and not Y[-1]["full"]:
        upto = last_month[5:]
        prev = {k: v for k, v in a["M"].items() if k[:4] == str(int(cur) - 1) and k[5:] <= upto}
        tot = defaultdict(float)
        for v in prev.values():
            for f in ("ts", "sp", "asl", "nd_ad", "nd_ts"):
                tot[f] += v.get(f, 0)
        Y[-1]["cmp"] = row(str(int(cur) - 1), tot, 10**6) if prev else None
    out = {"W": W, "M": Mo, "Y": Y}
    if mtd and "cur" in a["D"]:
        n = mtd_days(mtd)
        out["MTD"] = {"cur": row("MTD", a["D"]["cur"], n), "prior": row("MTD-prior", a["D"]["prior"], n) if "prior" in a["D"] else None}
    return out


# MerchantSpring (the source clients see): channelId -> hub client slug. Several stores can roll up into one
# account (Seller + Vendor Central, or an agency's brands). Stores not listed are not hub accounts.
MS_CHANNELS = {
    "94801626": "advanced-bionutritionals", "42580271": "bingo1525", "106902004": "bohemiaskin",
    "20313310": "boroux", "13585440": "cosmo-technologies", "93574878": "displate", "48122808": "dzg-products",
    "16035967": "inglesina", "117718061": "joes-trend", "13427311": "kensingtonvalleytrading",
    "13145540": "leading-choice-products", "107106228": "md-buildingproducts", "105122631": "md-buildingproducts",
    "102432899": "nutrivein", "13467156": "savongoods", "95420482": "shinewater", "81889729": "skysailconsumer",
    "47349140": "southerndental", "13428328": "spring-mount-supply", "31389730": "steam-clip",
    "101314217": "trailheads-apparel", "118288902": "turmskin", "13419844": "ultimate-footwear",
    "38104006": "ultimate-footwear", "114883607": "ultimate-washer", "66964067": "versa-group",
    "67364816": "versa-group", "99754043": "altun", "51216696": "altun", "87238171": "altun",
    "105539804": "altun", "100722276": "nature-blends", "118847691": "sidekick", "118710086": "smart-cookie",
}
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def load_ms(msdir):
    """MerchantSpring getSalesByPeriod files (<channelId>_W.json / _M.json, each bucket carries the
    period plus the same-length prior period) -> {client: {"W"|"M": {key: {ts, sp, asl}}, "cur", "ads"}}."""
    out = {}
    def num(r, n):
        v = r.get(n)
        return float(v) if v not in (None, "") else 0.0
    for ch, client in MS_CHANNELS.items():
        f = os.path.join(msdir, f"{ch}_MTD.json")
        if os.path.exists(f):                       # month to date: daily rows, each with the same day of the month before
            d = json.load(open(f))
            a = out.setdefault(client, {"W": defaultdict(lambda: defaultdict(float)),
                                        "M": defaultdict(lambda: defaultdict(float)), "cur": d.get("currency", "USD"),
                                        "ads": False, "stores": set()})
            m = a.setdefault("D", {"cur": defaultdict(float), "prior": defaultdict(float)})
            for r in d["rows"]:
                for key, pre in (("cur", ""), ("prior", "prior")):
                    nm = lambda n: (pre + n[0].upper() + n[1:]) if pre else n
                    m[key]["ts"] += num(r, nm("sales")); m[key]["sp"] += num(r, nm("adSpend")); m[key]["asl"] += num(r, nm("adSales"))
                    if num(r, nm("adSpend")) > 0:
                        a["ads"] = True
        for g in ("W", "M"):
            f = os.path.join(msdir, f"{ch}_{g}.json")
            if not os.path.exists(f):
                continue
            d = json.load(open(f))
            a = out.setdefault(client, {"W": defaultdict(lambda: defaultdict(float)),
                                        "M": defaultdict(lambda: defaultdict(float)), "cur": d.get("currency", "USD"),
                                        "ads": False, "stores": set()})
            a["stores"].add(ch)
            for r in d["rows"]:
                if g == "W":
                    dd, mm, yy = map(int, r["startTime"].split("/"))
                    k = date(yy, mm, dd); kp = k - timedelta(days=7 * len(d["rows"]))
                    k, kp = k.isoformat(), kp.isoformat()
                else:
                    mo, yy = r["startTime"].split(); k = f"{yy}-{MON[mo]:02d}"; kp = f"{int(yy) - 1}-{MON[mo]:02d}"
                for key, pre in ((k, ""), (kp, "prior")):
                    c = a[g][key]
                    f_ = (lambda n: float(r[pre + n[0].upper() + n[1:]] if pre else r[n]))
                    c["ts"] += f_("sales"); c["sp"] += f_("adSpend"); c["asl"] += f_("adSales")
                    if f_("adSpend") > 0:
                        a["ads"] = True
    return out


def ms_series(a):
    """Rows for the page from one MerchantSpring account. Leading periods before the store had data are dropped;
    ads show as missing when the account has no ad spend at all in the window."""
    def rows(g):
        ks = sorted(a[g]); out = []; started = False
        for k in ks:
            c = a[g][k]
            if not started and c["ts"] == 0 and c["sp"] == 0:
                continue
            started = True
            ts = round(c["ts"], 2) if c["ts"] else None
            sp = round(c["sp"], 2) if a["ads"] else None
            asl = round(c["asl"], 2) if a["ads"] else None
            out.append({"k": k, "ts": ts, "sp": sp, "asl": asl,
                        "acos": (sp / asl) if sp is not None and asl else None,
                        "tacos": (sp / ts) if sp is not None and ts else None, "pa": False, "pt": False})
        return out
    W, Mo = rows("W")[-25:], rows("M")[-25:]
    def one(k, c):
        ts = round(c["ts"], 2) if c["ts"] else None
        sp = round(c["sp"], 2) if a["ads"] else None
        asl = round(c["asl"], 2) if a["ads"] else None
        return {"k": k, "ts": ts, "sp": sp, "asl": asl, "acos": (sp / asl) if sp is not None and asl else None,
                "tacos": (sp / ts) if sp is not None and ts else None, "pa": False, "pt": False}
    D = a.get("D")
    MTD = {"cur": one("MTD", D["cur"]), "prior": one("MTD-prior", D["prior"])} if D else None     # latest 24 weeks / 24 months (+1 so the oldest shown has a % change)
    Y = []
    last = Mo[-1]["k"] if Mo else None
    for y in sorted({r["k"][:4] for r in Mo}):
        ms = [r for r in Mo if r["k"][:4] == y]
        if len(ms) < 12 and y != last[:4]:
            continue                               # partial year at the start of the 24-month window: skip
        tot = lambda f: (round(sum(r[f] for r in ms if r[f] is not None), 2) if any(r[f] is not None for r in ms) else None)
        ts, sp, asl = tot("ts"), tot("sp"), tot("asl")
        row = {"k": y, "ts": ts, "sp": sp, "asl": asl, "acos": (sp / asl) if sp is not None and asl else None,
               "tacos": (sp / ts) if sp is not None and ts else None, "pa": False, "pt": False,
               "months": [ms[0]["k"], ms[-1]["k"]], "full": len(ms) == 12}
        if not row["full"]:                        # YTD vs the same months of the year before
            upto = ms[-1]["k"][5:]
            pm = [r for r in Mo if r["k"][:4] == str(int(y) - 1) and r["k"][5:] <= upto]
            if pm:
                pts = sum(r["ts"] or 0 for r in pm); psp = sum(r["sp"] or 0 for r in pm) if sp is not None else None
                pas = sum(r["asl"] or 0 for r in pm) if sp is not None else None
                row["cmp"] = {"k": str(int(y) - 1), "ts": pts or None, "sp": psp, "asl": pas,
                              "acos": (psp / pas) if psp is not None and pas else None,
                              "tacos": (psp / pts) if psp is not None and pts else None}
        Y.append(row)
    out = {"W": W, "M": Mo, "Y": Y}
    if MTD:
        out["MTD"] = MTD
    return out


def build_rows(repo, raw, data_end, msdir=None, mtd=None):
    acc, meta = load(raw)
    hubs = {r["slug"]: r for r in M.rows(repo)}
    by_client = {re.sub(r"-[0-9a-f]{8}$", "", s): r for s, r in hubs.items()}
    out = []
    ms = load_ms(msdir) if msdir else {}
    for client, a in ms.items():
        h = by_client.get(client)
        if not h:
            continue
        out.append({"id": client, "client": client, "slug": h["slug"], "brand": h["brand"],
                    "cur": SYM.get(a["cur"], a["cur"] + " "), "src": "MerchantSpring",
                    "am": h["am"], "ppc": h["ppc"], "status": h["status"], "note": h["note"], "s": ms_series(a)})
    for key, (slug, label, cur) in meta.items():
        h = by_client.get(slug)
        if not h or slug in ms:
            continue
        out.append({"id": key, "client": slug, "slug": h["slug"], "brand": label or h["brand"], "cur": SYM.get(cur, cur + " "), "src": "Marketplace Ad Pros",
                    "am": h["am"], "ppc": h["ppc"], "status": h["status"], "note": h["note"],
                    "s": series(acc[key], data_end, mtd)})
    seen = {r["client"] for r in out}
    for client, h in by_client.items():             # hub accounts with no MAP data still get a row
        if client not in seen:
            out.append({"id": client, "client": client, "slug": h["slug"], "brand": h["brand"], "cur": "$",
                        "am": h["am"], "ppc": h["ppc"], "status": h["status"], "note": h["note"], "s": None})
    return sorted(out, key=lambda r: r["brand"].lower())


CSS = """
.tools { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin: 0 0 14px; }
.tools select, .tools input { font: inherit; font-size: 14px; padding: 8px 10px; border: 1px solid %(border)s;
  border-radius: 6px; background: #fff; color: %(ink)s; min-width: 0; }
.tools input { flex: 1 1 200px; }
.count { font-size: 12.5px; color: %(muted)s; }
.tabs-top { display:flex; gap:6px; margin: 0 0 18px; }
.tabs-top a { font-size: 13px; padding: 7px 14px; border: 1px solid %(border)s; border-radius: 6px; text-decoration: none; color: %(ink)s; background:#fff; }
.tabs-top a.on { background: %(dark)s; color: #fff; border-color: %(dark)s; }
.wrap { overflow-x: auto; background:#fff; border: 1px solid %(border)s; border-radius: 6px; }
table { width: 100%%; border-collapse: collapse; }
th, td { text-align: right; padding: 9px 12px; border-bottom: 1px solid %(border)s; font-size: 13.5px; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; }
thead th { background: %(dark)s; color: #fff; font-weight: 600; font-size: 11.5px; letter-spacing: .3px; text-transform: uppercase; position: sticky; top: 0; }
tr.acc { cursor: pointer; }
tr.acc:hover td { background: #fbf7ef; }
tr.acc.open td { background: #fff7e8; }
tr.acc td:first-child b { color: %(dark)s; }
.car { display:inline-block; width: 14px; color: %(muted)s; transition: transform .15s; }
tr.acc.open .car { transform: rotate(90deg); }
.who { font-size: 11.5px; color: %(muted)s; }
.v { display:block; }
.d { display:block; font-size: 11.5px; font-weight: 600; }
.up { color: %(good)s; } .dn { color: %(bad)s; } .nt { color: %(muted)s; }
.na { color: %(muted)s; }
.pill { display:inline-block; font-size: 11px; padding: 1px 7px; border-radius: 10px; border: 1px solid %(border)s; color: %(muted)s; margin-left: 6px; }
tr.det > td { background: #fafaf7; padding: 14px 16px 18px; }
.det-h { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom: 10px; }
.seg button { font: inherit; font-size: 12.5px; padding: 6px 14px; border: 1px solid %(border)s; background:#fff; cursor:pointer; }
.seg button:first-child { border-radius: 6px 0 0 6px; } .seg button:last-child { border-radius: 0 6px 6px 0; }
.seg button + button { border-left: 0; }
.seg button.on { background: %(dark)s; color:#fff; border-color: %(dark)s; }
.det-h a { font-size: 12.5px; color: %(dark)s; }
.det-r { display:flex; gap:14px; align-items:center; }
.dl { font: inherit; font-size: 12.5px; padding: 6px 12px; border: 1px solid %(border)s; border-radius: 6px; background:#fff; color: %(dark)s; cursor:pointer; }
.dl:hover { border-color: %(accent)s; }
.h2row { display:flex; justify-content:space-between; align-items:flex-end; gap:10px; border-bottom: 2px solid %(border)s; margin-bottom: 18px; padding-bottom: 10px; }
.h2row h2 { border: 0; margin: 0; padding: 0; }
.upd { font-size: 12.5px; color: %(muted)s; margin-top: 4px; }
.mini { max-height: 460px; overflow: auto; border: 1px solid %(border)s; border-radius: 6px; background:#fff; }
.mini th { background: #2b2f38; }
.mini td, .mini th { padding: 7px 12px; font-size: 13px; }
.mini td:first-child { font-weight: 600; }
.mini tr.yr td { background: #f1f2f4; font-weight: 600; text-align:left; font-size: 12px; color: %(muted)s; }
.flag { color: %(warn)s; font-weight: 600; margin-left: 2px; }
.notes { font-size: 12px; color: %(muted)s; margin-top: 10px; line-height: 1.6; }
@media (max-width: 720px) { th, td { padding: 7px 8px; font-size: 12.5px; } }
""" % dict(border=B.BORDER, ink=B.INK, dark=B.DARK, muted=B.MUTED, accent=B.ACCENT, good=B.GOOD, bad=B.BAD, warn=B.WARN)

JS = r"""
(function(){
var D = window.PERF, $ = function(i){ return document.getElementById(i); };
var MET = [["ts","Total Sales",1,"$"],["sp","Ad Spend",0,"$"],["asl","Ad Sales",1,"$"],["acos","ACoS",-1,"%"],["tacos","TACoS",-1,"%"]];
var MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function money(v, c){ if (v == null) return null; var a = Math.abs(v), s = a >= 1e6 ? (a/1e6).toFixed(2)+"M" : a >= 1e4 ? Math.round(a).toLocaleString("en-US") : a.toLocaleString("en-US",{minimumFractionDigits:2, maximumFractionDigits:2}); return (v<0?"-":"") + c + s; }
function pct(v){ return v == null ? null : (v*100).toFixed(2) + "%"; }
function fmt(m, v, c){ return m[3] === "%" ? pct(v) : money(v, c); }
function chg(a, b){ return (a == null || b == null || b === 0) ? null : (a - b) / Math.abs(b); }
function delta(m, d){
  if (d == null) return '<span class="d nt">&ndash;</span>';
  var cls = Math.abs(d) < 0.0005 ? "nt" : (m[2] === 0 ? "nt" : ((d > 0) === (m[2] > 0) ? "up" : "dn"));
  return '<span class="d ' + cls + '">' + (d > 0 ? "&#9650; +" : d < 0 ? "&#9660; " : "") + (d*100).toFixed(2) + '%</span>';
}
function cell(m, cur, prev, c, flag){
  var v = fmt(m, cur ? cur[m[0]] : null, c);
  if (v == null) return '<td><span class="v na">&ndash;</span></td>';
  return '<td><span class="v">' + v + (flag ? '<span class="flag" title="Partial coverage">*</span>' : '') + '</span>' + delta(m, prev ? chg(cur[m[0]], prev[m[0]]) : null) + '</td>';
}
function lbl(g, k){
  if (g === "M") { return MN[+k.slice(5)-1] + " " + k.slice(0,4); }
  if (g === "W") { var s = new Date(k + "T00:00:00Z"), e = new Date(s.getTime() + 6*864e5);
    return (s.getUTCMonth()+1) + "/" + s.getUTCDate() + " – " + (e.getUTCMonth()+1) + "/" + e.getUTCDate(); }
  return k;
}
function dshort(iso){ var d = new Date(iso + "T00:00:00Z"); return MN[d.getUTCMonth()] + " " + d.getUTCDate(); }
function mtdLbl(){ var m = D.mtd; return dshort(m.start) + "\u2013" + new Date(m.end + "T00:00:00Z").getUTCDate(); }
function mtdPrevLbl(){ var m = D.mtd; return dshort(m.pstart) + "\u2013" + new Date(m.pend + "T00:00:00Z").getUTCDate(); }
function mlab(k){ return MN[+k.slice(5)-1] + " " + k.slice(0,4); }
var VIEW = D.mtd ? "mtd" : "month";
function pick(a){      // [current, comparison] for the summary table in the selected view
  if (!a.s) return [null, null];
  if (VIEW === "mtd") return a.s.MTD ? [a.s.MTD.cur, a.s.MTD.prior] : [null, null];
  var Ms = a.s.M;
  for (var i = Ms.length - 1; i >= 0; i--) if (Ms[i].k === D.month) return [Ms[i], Ms[i-1] && Ms[i-1].k === D.prev ? Ms[i-1] : null];
  return [null, null];
}
function flags(m, r){ return (r.pa && (m[0] !== "ts")) || (r.pt && (m[0] === "ts" || m[0] === "tacos")); }
function mini(a, g){
  var rows = a.s[g].slice().reverse(), h = "", lastY = null;
  if (g !== "Y") rows = rows.slice(0, 24);
  if (!rows.length) return '<p class="na">No data for this view.</p>';
  rows.forEach(function(r, i){
    var py = a.s.Y[a.s.Y.length - 2 - i];
    var prev = g === "Y" ? (r.cmp || (r.full && py && py.full ? py : null)) : (a.s[g][a.s[g].length - 2 - i] || null);
    if (g === "W" && r.k.slice(0,4) !== lastY) { lastY = r.k.slice(0,4); h += '<tr class="yr"><td colspan="6">' + lastY + '</td></tr>'; }
    var L = lbl(g, r.k);
    if (g === "Y" && r.months && !r.full) L += ' <span class="pill">' + MN[+r.months[0].slice(5)-1] + "–" + MN[+r.months[1].slice(5)-1] + '</span>';
    if (g === "Y" && r.cmp) L += ' <span class="who">vs same months ' + r.cmp.k + '</span>';
    h += "<tr><td>" + L + "</td>" + MET.map(function(m){ return cell(m, r, prev, a.cur, flags(m, r)); }).join("") + "</tr>";
  });
  if (g === "M" && D.mtd && a.s.MTD) h = '<tr><td>' + mtdLbl() + ' <span class="pill">MTD</span> <span class="who">vs ' + mtdPrevLbl() + '</span></td>'
    + MET.map(function(m){ return cell(m, a.s.MTD.cur, a.s.MTD.prior, a.cur, false); }).join("") + "</tr>" + h;
  return '<div class="mini"><table><thead><tr><th>Data Range</th>' + MET.map(function(m){ return "<th>" + m[1] + "</th>"; }).join("") + "</tr></thead><tbody>" + h + "</tbody></table></div>";
}
function prevOf(a, g, i){   // i = index in the original (oldest-first) series
  var r = a.s[g][i];
  if (g !== "Y") return a.s[g][i-1] || null;
  var py = a.s.Y[i-1]; return r.cmp || (r.full && py && py.full ? py : null);
}
function num(v, m){ return v == null ? "" : (m[3] === "%" ? (v*100).toFixed(2) + "%" : v.toFixed(2)); }
function pc(d){ return d == null ? "" : (d*100).toFixed(2) + "%"; }
function q(x){ x = String(x); return /[",\n]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x; }
function save(name, rows){
  var csv = "\ufeff" + rows.map(function(r){ return r.map(q).join(","); }).join("\r\n");
  var url = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
  var l = document.createElement("a"); l.href = url; l.download = name; document.body.appendChild(l); l.click();
  setTimeout(function(){ URL.revokeObjectURL(url); l.remove(); }, 0);
}
var HDR = []; MET.forEach(function(m){ HDR.push(m[1], m[1] + " % chg"); });
function csvAccount(a, g){
  var out = [["Data Range"].concat(HDR, ["Partial ads", "Partial sales"])];
  for (var i = a.s[g].length - 1; i >= Math.max(0, g === "Y" ? 0 : a.s[g].length - 24); i--) {
    var r = a.s[g][i], p = prevOf(a, g, i), L = lbl(g, r.k).replace("\u2013", "-");
    if (g === "W") L = r.k + " to " + new Date(new Date(r.k + "T00:00:00Z").getTime() + 6*864e5).toISOString().slice(0, 10);
    if (g === "Y" && r.months && !r.full) L += " (" + MN[+r.months[0].slice(5)-1] + "-" + MN[+r.months[1].slice(5)-1] + ")";
    var row = [L]; MET.forEach(function(m){ row.push(num(r[m[0]], m), pc(p ? chg(r[m[0]], p[m[0]]) : null)); });
    out.push(row.concat([r.pa ? "yes" : "", r.pt ? "yes" : ""]));
  }
  var G = {W: "weekly", M: "monthly", Y: "annual"}[g];
  save(a.brand.replace(/&#x27;|&amp;|[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") + "_performance_" + G + ".csv", out);
}
function csvSummary(){
  var curL = VIEW === "mtd" ? D.mtd.start + " to " + D.mtd.end : D.month, prevL = VIEW === "mtd" ? D.mtd.pstart + " to " + D.mtd.pend : D.prev;
  var out = [["Account", "AM", "PPC", "Status", "Currency"].concat(HDR.map(function(h){ return h.indexOf("% chg") > 0 ? h + " vs " + prevL : h + " " + curL; }))];
  shown.forEach(function(a){
    var row = [a.brand.replace(/&#x27;/g, "'").replace(/&amp;/g, "&"), a.am, a.ppc.join(", "), a.status, a.cur.trim()];
    var cp = pick(a), cur = cp[0], prev = cp[1];
    MET.forEach(function(m){ row.push(cur ? num(cur[m[0]], m) : "", cur && prev ? pc(chg(cur[m[0]], prev[m[0]])) : ""); });
    out.push(row);
  });
  save("performance_overview_" + (VIEW === "mtd" ? "mtd_" + D.mtd.end : D.month + "_vs_" + D.prev) + ".csv", out);
}
var body = $("rows"), open = {}, shown = [];
function render(){
  var t = $("q").value.trim().toLowerCase(), am = $("am").value, ppc = $("ppc").value, st = $("st").value, n = 0, h = ""; shown = [];
  D.rows.forEach(function(a){
    var s = a.status;
    var ok = (!t || (a.brand + " " + a.note).toLowerCase().indexOf(t) >= 0) && (!am || a.am === am)
      && (!ppc || a.ppc.indexOf(ppc) >= 0) && (st === "" || (st === "current" ? s !== "inactive" : s === st));
    if (!ok) return; n++; shown.push(a);
    var who = '<div class="who">' + [a.am, a.ppc.join(", ")].filter(Boolean).join(" · ") + '</div>';
    var tag = s !== "active" ? '<span class="pill">' + s.charAt(0).toUpperCase() + s.slice(1) + '</span>' : "";
    if (!a.s) { h += '<tr><td><span class="car"></span><b>' + a.brand + '</b>' + tag + who + '</td><td colspan="5" style="text-align:left" class="na">Not connected in MerchantSpring</td></tr>'; return; }
    var cp = pick(a), cur = cp[0], prev = cp[1];
    h += '<tr class="acc' + (open[a.id] ? " open" : "") + '" data-id="' + a.id + '"><td><span class="car">&#9656;</span><b>' + a.brand + '</b>' + tag + who + '</td>'
      + MET.map(function(m){ return cell(m, cur, prev, a.cur, false); }).join("") + "</tr>";
    if (open[a.id]) {
      var g = open[a.id];
      h += '<tr class="det"><td colspan="6"><div class="det-h"><div class="seg" data-id="' + a.id + '">'
        + [["W","Weekly"],["M","Monthly"],["Y","Annual"]].map(function(x){ return '<button data-g="' + x[0] + '"' + (g === x[0] ? ' class="on"' : '') + '>' + x[1] + '</button>'; }).join("")
        + '</div><div class="det-r"><span class="who">Source: ' + a.src + '</span><button class="dl" data-csv="' + a.id + '">Download CSV</button><a href="../accounts/' + a.slug + '/">Open account hub &rarr;</a></div></div>' + mini(a, g) + '</td></tr>';
    }
  });
  var T = VIEW === "mtd" ? ["Month to date &middot; " + mtdLbl() + " vs " + mtdPrevLbl(), mtdLbl() + " (month to date) value, and the change vs the same days of the month before (" + mtdPrevLbl() + ")."]
    : [mlab(D.month) + " vs " + mlab(D.prev), mlab(D.month) + " value, and the change vs " + mlab(D.prev) + "."];
  $("ttl").innerHTML = "Performance Overview &middot; " + T[0]; $("cellnote").innerHTML = "Each cell: " + T[1];
  [].forEach.call(document.querySelectorAll("#view button"), function(b){ b.className = b.getAttribute("data-v") === VIEW ? "on" : ""; });
  body.innerHTML = h || '<tr><td colspan="6" class="na">No accounts match the filters.</td></tr>';
  $("count").textContent = n + " account" + (n === 1 ? "" : "s");
  try { localStorage.setItem("xp-hub-f", JSON.stringify({am: am, ppc: ppc, st: st})); } catch (e) {}
}
body.addEventListener("click", function(e){
  var b = e.target.closest(".seg button");
  if (b) { open[b.parentNode.getAttribute("data-id")] = b.getAttribute("data-g"); render(); return; }
  var c = e.target.closest("[data-csv]");
  if (c) { var id = c.getAttribute("data-csv"); D.rows.forEach(function(a){ if (a.id === id) csvAccount(a, open[id] || "M"); }); return; }
  if (e.target.closest("a") || e.target.closest(".det")) return;
  var tr = e.target.closest("tr.acc"); if (!tr) return;
  var id = tr.getAttribute("data-id"); if (open[id]) delete open[id]; else open[id] = "M"; render();
});
try { var f = JSON.parse(localStorage.getItem("xp-hub-f") || "{}"); ["am","ppc","st"].forEach(function(k){ if (f[k] !== undefined) $(k).value = f[k]; }); } catch (e) {}
$("dl-all").addEventListener("click", csvSummary);
$("view").addEventListener("click", function(e){ var b = e.target.closest("button"); if (b) { VIEW = b.getAttribute("data-v"); render(); } });
["am","ppc","st"].forEach(function(k){ $(k).addEventListener("change", render); }); $("q").addEventListener("input", render);
render();
})();
"""


def page(rows, data_end, today, mtd=None):
    last = (data_end.replace(day=1) - timedelta(days=1)) if data_end.day < calendar.monthrange(data_end.year, data_end.month)[1] else data_end
    month = last.strftime("%Y-%m"); prev = (last.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    mlab = lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y")
    ams = sorted({r["am"] for r in rows if r["am"]}); ppcs = sorted({p for r in rows for p in r["ppc"]})
    sel = lambda id_, lab, vals: (f'<select id="{id_}" aria-label="{lab}"><option value="">{lab}: all</option>'
                                  + "".join(f'<option value="{esc(v)}">{lab}: {esc(v)}</option>' for v in vals) + "</select>")
    md = lambda iso: date.fromisoformat(iso)
    hero = (f"Month to date {md(mtd['start']).strftime('%b %-d')}\u2013{md(mtd['end']).day} vs {md(mtd['pstart']).strftime('%b %-d')}\u2013{md(mtd['pend']).day}"
            if mtd else f"{mlab(month)} vs {mlab(prev)}")
    data = json.dumps({"month": month, "prev": prev, "mtd": mtd, "rows": [{k: (esc(v) if k in ("brand", "note") else v) for k, v in r.items()} for r in rows]},
                      separators=(",", ":")).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>XP Strategy Analysis - Performance Overview</title>
<style>{P.HUB_CSS}{H.HEADER_CSS}{CSS}
.xph-meta > div:last-child {{ display: none; }}
</style></head><body>
{H.hero_html("Performance Overview", P.logo_b64(), "US", today, hero)}
<main>
<div class="tabs-top"><a href="./">Account Hubs</a><a class="on" href="performance.html">Performance Overview</a><a href="changes.html">Weekly Changes</a></div>
<div class="h2row"><div><h2 id="ttl">Performance Overview &middot; {mlab(month)} vs {mlab(prev)}</h2>
<div class="upd">Last updated {date.fromisoformat(today).strftime("%b %-d, %Y")} &middot; data through {data_end.strftime("%b %-d, %Y")} &middot; weekly view through week of {(data_end - timedelta(days=6)).strftime("%b %-d")}{(" &middot; month to date through " + date.fromisoformat(mtd["end"]).strftime("%b %-d")) if mtd else ""}</div></div><button class="dl" id="dl-all" title="Accounts currently shown, with the filters applied">Download CSV</button></div>
{('<div class="seg" id="view" style="margin:0 0 12px"><button data-v="mtd">Month to date</button><button data-v="month">Last full month &middot; ' + mlab(month) + '</button></div>') if mtd else '<div id="view"></div>'}
<div class="tools">
  {sel("am", "AM", ams)}{sel("ppc", "PPC", ppcs)}
  <select id="st" aria-label="Status"><option value="current">Current accounts</option><option value="inactive">Inactive</option><option value="">All accounts</option></select>
  <input id="q" type="search" placeholder="Filter accounts" aria-label="Filter accounts">
  <span class="count" id="count"></span>
</div>
<div class="wrap"><table><thead><tr><th>Account &middot; click for weekly, monthly, annual</th><th>Total Sales</th><th>Ad Spend</th><th>Ad Sales</th><th>ACoS</th><th>TACoS</th></tr></thead>
<tbody id="rows"></tbody></table></div>
<p class="notes"><span id="cellnote">Each cell: {mlab(month)} value, and the change vs {mlab(prev)}.</span> Green = better, red = worse (higher ACoS and TACoS are worse); Ad Spend change is neutral.
Source: MerchantSpring, the same numbers clients see (Badass Moto from Marketplace Ad Pros, as it is not connected in MerchantSpring). Total Sales = MerchantSpring sales excluding tax, Seller Central plus Vendor Central where an account has both.
Ad Spend and Ad Sales = MerchantSpring advertising. ACoS = Ad Spend / Ad Sales. TACoS = Ad Spend / Total Sales. US marketplace only (UK for Nature Blends and Badass Moto Europe).
Month to date is refreshed with the weekly run, so the most recent days (Vendor Central and late ad attribution) can still move. History: last 24 full weeks (Sun&ndash;Sat) and last 24 full months; the current year is compared with the same months of the year before. &ndash; = not connected for that period.</p>
<p class="source" style="font-size:12px;color:{B.MUTED};margin-top:6px">Source: MerchantSpring (sales and advertising by store), weeks through {data_end.strftime("%b %-d, %Y")}, months through {mlab(month)}. AM and PPC from tools/account_team.json.</p>
</main>
{H.footer_html(B.DISCLAIMER, f"data through {data_end.strftime('%b %-d, %Y')}", "Performance Overview", today)}
<script>window.PERF = {data};</script>
<script>{JS}</script>
</body></html>"""


def build(repo, raw, data_end, msdir=None, mtd_end=None):
    mtd = None
    if mtd_end:
        pm_end = mtd_end.replace(day=1) - timedelta(days=1)
        pend = pm_end.replace(day=min(mtd_end.day, pm_end.day))
        mtd = {"start": mtd_end.replace(day=1).isoformat(), "end": mtd_end.isoformat(),
               "pstart": pend.replace(day=1).isoformat(), "pend": pend.isoformat()}
    rows = build_rows(repo, raw, data_end, msdir, mtd)
    if mtd and not any(r["s"] and r["s"].get("MTD") for r in rows):
        mtd = None
    p = os.path.join(repo, "hub", "performance.html")
    open(p, "w").write(page(rows, data_end, date.today().isoformat(), mtd))
    return p, rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="."); ap.add_argument("--raw", required=True)
    ap.add_argument("--ms", help="folder of MerchantSpring <channelId>_W.json / _M.json files (preferred source)")
    ap.add_argument("--data-end", required=True, help="last full day of MAP data, yyyy-mm-dd")
    ap.add_argument("--mtd-end", help="last day of the month-to-date window, yyyy-mm-dd (usually yesterday); "
                    "needs <channelId>_MTD.json files and, for MAP accounts, g='D' rows with k 'cur' / 'prior'")
    a = ap.parse_args()
    p, rows = build(a.repo, a.raw, date.fromisoformat(a.data_end), a.ms, date.fromisoformat(a.mtd_end) if a.mtd_end else None)
    print("[done]", p, len(rows), "accounts,", sum(1 for r in rows if r["s"]), "with MAP data")
