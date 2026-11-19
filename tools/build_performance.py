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
    acc = defaultdict(lambda: {"W": defaultdict(lambda: defaultdict(float)), "M": defaultdict(lambda: defaultdict(float))})
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


def series(acc_key, data_end):
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
    return {"W": W, "M": Mo, "Y": Y}


def build_rows(repo, raw, data_end):
    acc, meta = load(raw)
    hubs = {r["slug"]: r for r in M.rows(repo)}
    by_client = {re.sub(r"-[0-9a-f]{8}$", "", s): r for s, r in hubs.items()}
    out = []
    for key, (slug, label, cur) in meta.items():
        h = by_client.get(slug)
        if not h:
            continue
        out.append({"id": key, "client": slug, "slug": h["slug"], "brand": label or h["brand"], "cur": SYM.get(cur, cur + " "),
                    "am": h["am"], "ppc": h["ppc"], "status": h["status"], "note": h["note"],
                    "s": series(acc[key], data_end)})
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
.mini { max-height: 460px; overflow: auto; border: 1px solid %(border)s; border-radius: 6px; background:#fff; }
.mini th { background: #2b2f38; }
.mini td, .mini th { padding: 7px 12px; font-size: 13px; }
.mini td:first-child { font-weight: 600; }
.mini tr.yr td { background: #f1f2f4; font-weight: 600; text-align:left; font-size: 12px; color: %(muted)s; }
.flag { color: %(warn)s; font-weight: 600; margin-left: 2px; }
.notes { font-size: 12px; color: %(muted)s; margin-top: 10px; line-height: 1.6; }
@media (max-width: 720px) { th, td { padding: 7px 8px; font-size: 12.5px; } }
""" % dict(border=B.BORDER, ink=B.INK, dark=B.DARK, muted=B.MUTED, good=B.GOOD, bad=B.BAD, warn=B.WARN)

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
function flags(m, r){ return (r.pa && (m[0] !== "ts")) || (r.pt && (m[0] === "ts" || m[0] === "tacos")); }
function mini(a, g){
  var rows = a.s[g].slice().reverse(), h = "", lastY = null;
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
  return '<div class="mini"><table><thead><tr><th>Data Range</th>' + MET.map(function(m){ return "<th>" + m[1] + "</th>"; }).join("") + "</tr></thead><tbody>" + h + "</tbody></table></div>";
}
var body = $("rows"), open = {};
function render(){
  var t = $("q").value.trim().toLowerCase(), am = $("am").value, ppc = $("ppc").value, st = $("st").value, n = 0, h = "";
  D.rows.forEach(function(a){
    var s = a.status;
    var ok = (!t || (a.brand + " " + a.note).toLowerCase().indexOf(t) >= 0) && (!am || a.am === am)
      && (!ppc || a.ppc.indexOf(ppc) >= 0) && (st === "" || (st === "current" ? s !== "inactive" : s === st));
    if (!ok) return; n++;
    var who = '<div class="who">' + [a.am, a.ppc.join(", ")].filter(Boolean).join(" · ") + '</div>';
    var tag = s !== "active" ? '<span class="pill">' + s.charAt(0).toUpperCase() + s.slice(1) + '</span>' : "";
    if (!a.s) { h += '<tr><td><span class="car"></span><b>' + a.brand + '</b>' + tag + who + '</td><td colspan="5" style="text-align:left" class="na">Not connected in Marketplace Ad Pros</td></tr>'; return; }
    var Ms = a.s.M, cur = null, prev = null;
    for (var i = Ms.length - 1; i >= 0; i--) if (Ms[i].k === D.month) { cur = Ms[i]; prev = Ms[i-1] && Ms[i-1].k === D.prev ? Ms[i-1] : null; break; }
    h += '<tr class="acc' + (open[a.id] ? " open" : "") + '" data-id="' + a.id + '"><td><span class="car">&#9656;</span><b>' + a.brand + '</b>' + tag + who + '</td>'
      + MET.map(function(m){ return cell(m, cur, prev, a.cur, false); }).join("") + "</tr>";
    if (open[a.id]) {
      var g = open[a.id];
      h += '<tr class="det"><td colspan="6"><div class="det-h"><div class="seg" data-id="' + a.id + '">'
        + [["W","Weekly"],["M","Monthly"],["Y","Annual"]].map(function(x){ return '<button data-g="' + x[0] + '"' + (g === x[0] ? ' class="on"' : '') + '>' + x[1] + '</button>'; }).join("")
        + '</div><a href="../accounts/' + a.slug + '/">Open account hub &rarr;</a></div>' + mini(a, g) + '</td></tr>';
    }
  });
  body.innerHTML = h || '<tr><td colspan="6" class="na">No accounts match the filters.</td></tr>';
  $("count").textContent = n + " account" + (n === 1 ? "" : "s");
  try { localStorage.setItem("xp-hub-f", JSON.stringify({am: am, ppc: ppc, st: st})); } catch (e) {}
}
body.addEventListener("click", function(e){
  var b = e.target.closest(".seg button");
  if (b) { open[b.parentNode.getAttribute("data-id")] = b.getAttribute("data-g"); render(); return; }
  if (e.target.closest("a") || e.target.closest(".det")) return;
  var tr = e.target.closest("tr.acc"); if (!tr) return;
  var id = tr.getAttribute("data-id"); if (open[id]) delete open[id]; else open[id] = "M"; render();
});
try { var f = JSON.parse(localStorage.getItem("xp-hub-f") || "{}"); ["am","ppc","st"].forEach(function(k){ if (f[k] !== undefined) $(k).value = f[k]; }); } catch (e) {}
["am","ppc","st"].forEach(function(k){ $(k).addEventListener("change", render); }); $("q").addEventListener("input", render);
render();
})();
"""


def page(rows, data_end, today):
    last = (data_end.replace(day=1) - timedelta(days=1)) if data_end.day < calendar.monthrange(data_end.year, data_end.month)[1] else data_end
    month = last.strftime("%Y-%m"); prev = (last.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    mlab = lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y")
    ams = sorted({r["am"] for r in rows if r["am"]}); ppcs = sorted({p for r in rows for p in r["ppc"]})
    sel = lambda id_, lab, vals: (f'<select id="{id_}" aria-label="{lab}"><option value="">{lab}: all</option>'
                                  + "".join(f'<option value="{esc(v)}">{lab}: {esc(v)}</option>' for v in vals) + "</select>")
    data = json.dumps({"month": month, "prev": prev, "rows": [{k: (esc(v) if k in ("brand", "note") else v) for k, v in r.items()} for r in rows]},
                      separators=(",", ":")).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>XP Strategy Analysis - Performance Overview</title>
<style>{P.HUB_CSS}{H.HEADER_CSS}{CSS}
.xph-meta > div:last-child {{ display: none; }}
</style></head><body>
{H.hero_html("Performance Overview", P.logo_b64(), "US", today, f"{mlab(month)} vs {mlab(prev)}")}
<main>
<div class="tabs-top"><a href="./">Account Hubs</a><a class="on" href="performance.html">Performance Overview</a></div>
<h2>Performance Overview &middot; {mlab(month)} vs {mlab(prev)}</h2>
<div class="tools">
  {sel("am", "AM", ams)}{sel("ppc", "PPC", ppcs)}
  <select id="st" aria-label="Status"><option value="current">Current accounts</option><option value="inactive">Inactive</option><option value="">All accounts</option></select>
  <input id="q" type="search" placeholder="Filter accounts" aria-label="Filter accounts">
  <span class="count" id="count"></span>
</div>
<div class="wrap"><table><thead><tr><th>Account &middot; click for weekly, monthly, annual</th><th>Total Sales</th><th>Ad Spend</th><th>Ad Sales</th><th>ACoS</th><th>TACoS</th></tr></thead>
<tbody id="rows"></tbody></table></div>
<p class="notes">Each cell: {mlab(month)} value, and the change vs {mlab(prev)}. Green = better, red = worse (higher ACoS and TACoS are worse); Ad Spend change is neutral.
Total Sales = Seller Central ordered product sales + Vendor Central ordered revenue. Ad Spend and Ad Sales = Sponsored Products, Brands and Display (14-day attribution).
ACoS = Ad Spend / Ad Sales. TACoS = Ad Spend / Total Sales. US marketplace only (UK for Badass Moto Europe). Only complete weeks (Sun&ndash;Sat) and months are shown;
the current year is compared with the same months of the year before. <span class="flag">*</span> = source covers only part of the period (MAP ad history starts January 2026). &ndash; = source not connected in MAP for that period.</p>
<p class="source" style="font-size:12px;color:{B.MUTED};margin-top:6px">Source: Marketplace Ad Pros (Amazon Ads, Seller Central sales &amp; traffic, Vendor Central sales), data through {data_end.strftime("%b %-d, %Y")}. AM and PPC from tools/account_team.json.</p>
</main>
{H.footer_html(B.DISCLAIMER, f"data through {data_end.strftime('%b %-d, %Y')}", "Performance Overview", today)}
<script>window.PERF = {data};</script>
<script>{JS}</script>
</body></html>"""


def build(repo, raw, data_end):
    rows = build_rows(repo, raw, data_end)
    p = os.path.join(repo, "hub", "performance.html")
    open(p, "w").write(page(rows, data_end, date.today().isoformat()))
    return p, rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="."); ap.add_argument("--raw", required=True)
    ap.add_argument("--data-end", required=True, help="last full day of MAP data, yyyy-mm-dd")
    a = ap.parse_args()
    p, rows = build(a.repo, a.raw, date.fromisoformat(a.data_end))
    print("[done]", p, len(rows), "accounts,", sum(1 for r in rows if r["s"]), "with MAP data")
