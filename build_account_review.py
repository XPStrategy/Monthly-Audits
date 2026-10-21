#!/usr/bin/env python3
"""Build <Brand>_Monthly_Account_Review.html from findings.json.

Internal, data-only monthly review for account managers. Reuses the XP
Strategy brand lock, CSS and donut helper from the amazon-ads-prospect-audit
skill so both deliverables share one look. No scores, no recommendations.
"""
import argparse, json, os, re, sys, datetime as dt

import glob
_cands = [os.environ.get("XP_AUDIT_SCRIPTS", "")]
for _name in ("xp-audit-prospect", "amazon-ads-prospect-audit"):      # renamed prospect skill first, old name as fallback
    for _root in ("/mnt/skills", os.path.expanduser("~/.claude/skills"), "/root/.claude/skills"):
        _cands += glob.glob(os.path.join(_root, "**", _name, "scripts"), recursive=True)
AUDIT_SCRIPTS = next((c for c in _cands if c and os.path.exists(os.path.join(c, "build_showcase.py"))), "/mnt/skills/plugins/amazon-ads-prospect-audit/scripts")
sys.path.insert(0, AUDIT_SCRIPTS)
import brand as B                                                    # noqa: E402
from build_showcase import CSS as BASE_CSS, esc, donut, load_logo_b64, _CHART_JS, _month_label  # noqa: E402

PAL = B.CATEGORY_PALETTE
C_TY, C_LY, C_SPEND, C_LINE, C_LINE2 = PAL[2], "#a3a3a3", PAL[0], B.ACCENT, B.MUTED

EXTRA_CSS = """
body { font-feature-settings: "calt" 0, "liga" 0; font-variant-ligatures: none; }
.kpi-cards { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:24px; }
@media (max-width: 900px) { .kpi-cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 520px) { .kpi-cards { grid-template-columns: 1fr; } }
.kc { background:%(card)s; border:1px solid %(border)s; border-radius:6px; padding:14px 14px 8px; }
.kc-top { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.kc-label { font-size:11px; color:%(muted)s; text-transform:uppercase; letter-spacing:.5px; }
.kc-val { font-size:22px; font-weight:600; color:%(dark)s; margin:4px 0 2px; }
.kc-d { font-size:11.5px; color:%(muted)s; }
.kc svg { display:block; width:100%%; height:auto; margin-top:6px; }
.up-bad { color:%(bad)s; } .up-good { color:%(good)s; } .neu { color:%(muted)s; }
td.num, th.num { text-align:right !important; }
.trunc { max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.table-scroll { overflow-x:auto; max-width:100%%; }
td .pill-flag { margin:1px 0; white-space:normal; display:inline-block; max-width:130px; line-height:1.3; }
td.flags { white-space:normal; min-width:140px; }
details summary { cursor:pointer; font-size:13px; color:#666; margin-top:6px; }
.donut-row > *, .two-col > *, .three-col > * { min-width:0; }
@media (max-width: 720px) { .donut-row.single { grid-template-columns: 1fr; } .hbar .n { width:120px; } main { padding:20px 16px 40px; } .hero { padding:24px 16px; } .hero-inner { flex-direction:column; align-items:flex-start; gap:10px; } .hero-meta { text-align:left; } }
.pill { display:inline-block; padding:2px 7px; border-radius:3px; font-size:10px; font-weight:700; white-space:nowrap; }
.pill-PRIME { background:#eaf6ee; color:#1e7c3a; } .pill-STRONG { background:#fff8e1; color:#8a6d1a; }
.pill-WATCH, .pill-flag { background:#fdecea; color:#b02a1c; }
.pill-cls { background:#f1efe9; color:%(ink)s; font-weight:500; }
.pill-ok { background:#eaf6ee; color:#1e7c3a; } .pill-off { background:#f5f5f5; color:%(muted)s; }
.split-bar { display:flex; height:28px; border-radius:4px; overflow:hidden; margin:8px 0 6px; }
.split-bar span { display:block; height:100%%; }
.split-leg { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:%(muted)s; }
.split-leg i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:middle; }
.three-col { display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-bottom:20px; }
@media (max-width: 900px) { .three-col { grid-template-columns: 1fr; } }
.stat { background:%(card)s; border:1px solid %(border)s; border-radius:6px; padding:14px 18px; }
.stat .v { font-size:26px; font-weight:700; color:%(dark)s; margin-top:6px; }
.stat .s { font-size:11.5px; color:%(muted)s; margin-top:4px; line-height:1.4; }
.stat.bad { border-left:3px solid %(bad)s; } .stat.warn { border-left:3px solid %(warn)s; } .stat.good { border-left:3px solid %(good)s; }
.stat.info { border-left:3px solid %(accent)s; }
.note { font-size:12px; color:%(muted)s; margin:-6px 0 18px; }
.hbar { display:flex; align-items:center; gap:8px; font-size:12px; margin:5px 0; }
.hbar .n { width:210px; flex:none; color:%(ink)s; }
.hbar .t { flex:1; background:#f1efe9; height:12px; border-radius:2px; overflow:hidden; }
.hbar .t span { display:block; height:100%%; }
.hbar .v { width:60px; text-align:right; color:%(dark)s; font-weight:600; }
.alerts { list-style:none; margin:0; padding:0; }
.alerts li { display:flex; gap:10px; align-items:flex-start; padding:9px 0; border-top:1px solid %(border)s; font-size:13px; line-height:1.45; }
.alerts li:first-child { border-top:none; }
.alerts .lvl { flex:none; width:56px; text-align:center; }
.alerts .area { flex:none; width:110px; color:%(muted)s; font-size:12px; padding-top:1px; }
.alerts .txt { flex:1; min-width:0; color:%(ink)s; }
.alerts a { color:%(muted)s; font-size:12px; white-space:nowrap; }
.pill-high { background:#fdecea; color:#b02a1c; } .pill-watch { background:#fff8e1; color:#8a6d1a; } .pill-info { background:#f1efe9; color:%(ink)s; }
@media (max-width: 620px) { .alerts li { flex-wrap:wrap; } .alerts .area { width:auto; } }
.kc svg rect:hover { opacity:.75; }
.foot-dates { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:6px 18px; margin:12px 0 4px; font-size:12px; text-align:left; }
.foot-dates b { font-weight:600; }
""" % dict(dark=B.DARK, ink=B.INK, accent=B.ACCENT, muted=B.MUTED, card=B.CARD, border=B.BORDER,
           good=B.GOOD, warn=B.WARN, bad=B.BAD)

NAV = [("overview", "Overview"), ("trends", "Trends"), ("ad_spend", "Ad Spend"), ("strategy", "Strategy"),
       ("campaigns", "Campaigns"), ("wasted", "Wasted Spend"), ("harvest", "Harvest"),
       ("products", "Products"), ("budgets", "Budgets & Q4")]


SECTION_SOURCES = {
    "overview": "Seller Central Business Reports and Amazon Ads campaign reports",
    "trends": "Seller Central Business Reports and Amazon Ads campaign reports",
    "ad_spend": "Amazon Ads campaign, search term and placement reports",
    "strategy": "Amazon Ads search term, keyword and advertised product reports",
    "campaigns": "Amazon Ads campaign and search term reports; Amazon Ads budget recommendations",
    "wasted": "Amazon Ads search term reports, conversion-complete window",
    "harvest": "Amazon Ads search term reports, conversion-complete window; Brand Analytics Search Query Performance",
    "products": "Amazon Ads advertised product reports; Seller Central Business Reports and FBA inventory planning report",
    "budgets": "Amazon Ads budget recommendations; Seller Central Business Reports",
}
NO_SC_SOURCES = {"overview": "Amazon Ads campaign reports", "trends": "Amazon Ads campaign reports",
                 "harvest": "Amazon Ads search term reports, conversion-complete window",
                 "products": "Amazon Ads advertised product reports", "budgets": "Amazon Ads budget recommendations"}
_BOUND = re.compile(r'<table|<h2|<h3|<h4|</section>')


def add_source_captions(section_html, has_sc=True):
    """Same rule as the prospect audit: a 'Source: ...' caption after every table group and chart group."""
    m = re.search(r'<section id="([^"]+)"', section_html or "")
    if not m:
        return section_html
    sid = m.group(1)
    src = SECTION_SOURCES.get(sid, "Amazon Ads reports") if has_sc else NO_SC_SOURCES.get(sid, SECTION_SOURCES.get(sid, "Amazon Ads reports"))
    cap = f'<p class="src">Source: {esc(src)}</p>'
    out, pos = [], 0
    for t in re.finditer(r'</table>|<!--chart-end-->', section_html):
        end = t.end(); nxt = _BOUND.search(section_html, end)
        stop = nxt.start() if nxt else len(section_html)
        if 'class="src"' in section_html[end:stop]:
            continue
        out.append(section_html[pos:end]); out.append(cap); pos = end
    out.append(section_html[pos:])
    return "".join(out)


def drange(a, b):
    f = lambda d: dt.date.fromisoformat(d).strftime("%b %-d, %Y")
    return f"{f(a)} – {f(b)}"


def short_range(a, b):
    f = lambda d: dt.date.fromisoformat(d).strftime("%b %-d")
    return f"{f(a)} – {f(b)}"


# ---------------------------------------------------------------- format --
def money(v, d=0):
    return "—" if v is None else f"${v:,.{d}f}"


def pct(v, d=1):
    return "—" if v is None else f"{v*100:.{d}f}%"


def num(v):
    return "—" if v is None else f"{v:,.0f}"


def fmtv(v, f):
    return {"money": lambda x: money(x), "money2": lambda x: money(x, 2), "int": num, "pct": pct,
            "pct2": lambda x: pct(x, 2), "x": lambda x: "—" if x is None else f"{x:.2f}"}[f](v)


def delta(d, fmt, better):
    if d is None:
        return '<span class="neu">—</span>'
    is_pts = fmt == "pct"
    txt = f"{d*100:+.1f} pts" if is_pts else f"{d*100:+.1f}%"
    if better == "neutral" or abs(d) < (0.0005 if is_pts else 0.005):
        return f'<span class="neu">{txt}</span>'
    good = (d > 0) == (better == "up")
    return f'<span class="{"up-good" if good else "up-bad"}">{txt}</span>'


# ---------------------------------------------------------------- charts --
def combo_chart(labels, bars, lines=(), w=780, h=280, left_fmt="money", right_fmt="pct", label_every=1, tip_labels=None):
    """bars: [(name, values, color)] grouped; lines: [(name, values, color, dash)] on right axis.
    Hover / tap shows a tooltip with every series for that column (prospect-audit chart pattern)."""
    n = len(labels); pl, pr, pt, pb = 62, 56 if lines else 16, 18, 34
    pw, ph = w - pl - pr, h - pt - pb
    bmax = max([v or 0 for _, vals, _ in bars for v in vals] + [1])
    lmax = max([v or 0 for _, vals, _, _ in lines for v in vals] + [0.0001]) * 1.1
    lf = (lambda v: money(v)) if left_fmt == "money" else num
    rf = (lambda v: pct(v, 2 if lmax < 0.2 else 1)) if right_fmt == "pct" else (lambda v: money(v, 2))
    o = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">']
    for gy in range(5):
        y = pt + ph * gy / 4
        o.append(f'<line x1="{pl}" y1="{y:.0f}" x2="{w-pr}" y2="{y:.0f}" stroke="#eee"/>')
        lv = bmax * (1 - gy / 4)
        ltxt = (f"${lv/1000:,.0f}K" if bmax >= 5000 else f"${lv:,.0f}") if left_fmt == "money" else (f"{lv/1000:,.0f}K" if bmax >= 5000 else f"{lv:,.0f}")
        o.append(f'<text x="{pl-6}" y="{y+3:.0f}" font-size="10" fill="#999" text-anchor="end">{ltxt}</text>')
        if lines:
            rv = lmax * (1 - gy / 4)
            rtxt = f"{rv*100:.0f}%" if right_fmt == "pct" else f"${rv:.2f}"
            o.append(f'<text x="{w-pr+6}" y="{y+3:.0f}" font-size="10" fill="#999">{rtxt}</text>')
    nb = len(bars); grp = pw / n * 0.72; bw = grp / max(nb, 1)
    xs = [pl + pw * (i + 0.5) / n for i in range(n)]
    for i in range(n):
        cx = xs[i]
        for j, (_, vals, col) in enumerate(bars):
            v = vals[i]
            if v is None:
                continue
            bh = ph * v / bmax
            o.append(f'<rect x="{cx - grp/2 + j*bw:.1f}" y="{pt+ph-bh:.1f}" width="{max(bw-1.5,1):.1f}" height="{bh:.1f}" fill="{col}"/>')
        if i % label_every == 0 or i == n - 1:
            o.append(f'<text x="{cx:.0f}" y="{h-10}" font-size="10" fill="#999" text-anchor="middle">{esc(labels[i])}</text>')
    ly = lambda v: pt + ph * (1 - (v or 0) / lmax)
    for _, vals, col, dash in lines:
        pts = [f"{xs[i]:.0f},{ly(v):.0f}" for i, v in enumerate(vals) if v is not None]
        if pts:
            da = f' stroke-dasharray="{dash}"' if dash else ""
            o.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" stroke-width="2.4"{da}/>')
            for p_ in pts:
                x, y = p_.split(",")
                o.append(f'<circle cx="{x}" cy="{y}" r="2.6" style="fill:{col}"/>')
    # hover layer (marker colours via style= so the palette scan stays clean)
    o.append(f'<line class="xpc-guide" x1="0" y1="{pt}" x2="0" y2="{pt+ph}" stroke="#bbb" stroke-dasharray="3,3" style="display:none"/>')
    tips = []
    for i in range(n):
        dots = "".join(f'<circle cx="{xs[i]:.0f}" cy="{ly(vals[i]):.0f}" r="4.2" style="fill:{col}"/>'
                       for _, vals, col, _ in lines if vals[i] is not None)
        o.append(f'<g class="xpc-dots" data-i="{i}" style="display:none">{dots}</g>')
        rows = [[nm, lf(vals[i]), col] for nm, vals, col in bars] + [[nm, rf(vals[i]), col] for nm, vals, col, _ in lines]
        tips.append({"m": esc((tip_labels or labels)[i]), "x": round(xs[i], 1), "rows": rows})
    cw = pw / n
    for i in range(n):
        o.append(f'<rect class="xpc-hit" data-i="{i}" x="{pl + cw*i:.1f}" y="{pt}" width="{cw:.1f}" height="{ph}" fill="transparent"/>')
    o.append("</svg>")
    leg = "".join(f'<div class="lg"><span style="background:{c}"></span>{esc(nm)}</div>' for nm, _, c in bars)
    leg += "".join(f'<div class="lg"><span style="background:{c}"></span>{esc(nm)}</div>' for nm, _, c, _ in lines)
    data_attr = esc(json.dumps({"w": w, "tips": tips}))
    return (f'<div class="chlegend">{leg}</div><div class="xpc" data-chart="{data_attr}">' + "".join(o)
            + '<div class="xpc-tip" role="tooltip"></div></div>' + _CHART_JS)


def mini_bars(vals, labels, color, ly=None, w=240, h=70, fmt=None, tips=None):
    vv = [v for v in vals + (ly or []) if v is not None]
    if not vv:
        return ""
    mx = max(vv) or 1; n = len(vals); bw = w / n
    o = [f'<svg viewBox="0 0 {w} {h+14}">']
    for i, v in enumerate(vals):
        if v is None:
            o.append(f'<rect x="{i*bw+1:.1f}" y="{h-2}" width="{bw-2:.1f}" height="2" fill="#a3a3a3"/>')
            continue
        bh = max(h * v / mx, 1)
        fill = B.ACCENT if i == n - 1 else color
        tt = f'<title>{esc(tips[i] if tips else labels[i])}: {fmt(v) if fmt else v}' + (f' (LY {fmt(ly[i])})' if ly and ly[i] is not None and fmt else '') + '</title>'
        o.append(f'<rect x="{i*bw+1:.1f}" y="0" width="{bw:.1f}" height="{h}" fill="transparent">{tt}</rect>')
        o.append(f'<rect x="{i*bw+1:.1f}" y="{h-bh:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" fill="{fill}">{tt}</rect>')
    if ly:
        pts = [f"{i*bw+bw/2:.1f},{h - h*v/mx:.1f}" for i, v in enumerate(ly) if v is not None]
        o.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#a3a3a3" stroke-width="1.6" stroke-dasharray="3,2"/>')
    o.append(f'<text x="0" y="{h+12}" font-size="9" fill="#999">{esc(labels[0])}</text>')
    o.append(f'<text x="{w}" y="{h+12}" font-size="9" fill="#999" text-anchor="end">{esc(labels[-1])}</text>')
    o.append("</svg>")
    return "".join(o)


def split_bar(parts):
    tot = sum(v for _, v, _ in parts) or 1
    bar = "".join(f'<span style="width:{v/tot*100:.2f}%;background:{c}" title="{esc(n)}"></span>' for n, v, c in parts)
    leg = "".join(f'<span><i style="background:{c}"></i>{esc(n)} · {money(v)} ({v/tot*100:.1f}%)</span>' for n, v, c in parts)
    return f'<div class="split-bar">{bar}</div><div class="split-leg">{leg}</div>'


def hbars(items, fmt=pct, color=PAL[2], cap=None):
    mx = cap or max((v for _, v in items if v is not None), default=1) or 1
    return "".join(
        f'<div class="hbar"><span class="n">{esc(n)}</span><span class="t"><span style="width:{min((v or 0)/mx,1)*100:.1f}%;background:{color}"></span></span>'
        f'<span class="v">{fmt(v)}</span></div>' for n, v in items)


def table(head, rows, cls="data compact"):
    th = "".join(f'<th class="{"num" if a else ""}">{h}</th>' for h, a in head)
    trs = "".join("<tr>" + "".join(f'<td class="{"num" if head[i][1] else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="table-scroll"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


# ---------------------------------------------------------------- tabs ----
def tab_overview(f):
    per = f["period"]; rows = {r["key"]: r for r in per["rows"]}; m = f["meta"]
    months = f["months"]; mlab = [x["month"][2:].replace("-", "/") for x in months]
    spec = [("total_sales", "total_sales", "total_sales_ly", PAL[2]), ("ad_sales", "ad_sales", None, PAL[2]),
            ("spend", "spend", None, PAL[0]), ("tacos", "tacos", None, PAL[1]), ("acos", "acos", None, PAL[1]),
            ("cpc", "cpc", None, PAL[3]), ("ctr", "ctr", None, PAL[3]), ("cvr", "cvr", None, PAL[3]),
            ("roas", "roas", None, PAL[3])]
    cards = []
    for key, mkey, lykey, col in spec:
        if key not in rows or len(cards) == 8:
            continue
        r = rows[key]
        vals = [x.get(mkey) for x in months] if mkey else []
        ly = [x.get(lykey) for x in months] if lykey else None
        yoy = f' &middot; YoY {delta(r["yoy"], r["fmt"], r["better"])}' if r["yoy"] is not None else ""
        cards.append(f'<div class="kc"><div class="kc-label">{esc(r["label"])}</div>'
                     f'<div class="kc-val">{fmtv(r["l30"], r["fmt"])}</div>'
                     f'<div class="kc-d">MoM {delta(r["mom"], r["fmt"], r["better"])}{yoy}</div>'
                     f'{mini_bars(vals, mlab, col, ly, fmt=lambda v, _f=r["fmt"]: fmtv(v, _f), tips=[_month_label(x["month"]) for x in months]) if vals else ""}</div>')
    trows = []
    for r in per["rows"]:
        trows.append([esc(r["label"]), fmtv(r["l30"], r["fmt"]), fmtv(r["p30"], r["fmt"]), delta(r["mom"], r["fmt"], r["better"]),
                      fmtv(r["ly"], r["fmt"]) if r["ly"] is not None else '<span class="neu">n/a</span>',
                      delta(r["yoy"], r["fmt"], r["better"]) if r["ly"] is not None else '<span class="neu">n/a</span>'])
    ptab = table([("Metric", 0), ("Last 30 Days", 1), ("Prior 30 Days", 1), ("MoM", 1), ("Same 30 Days LY", 1), ("YoY", 1)], trows)
    fb = m.get("first_by_type", {})
    atn = {"SP": "SP", "SB": "SB", "SBV": "SB Video", "SD": "SD"}
    hist = ", ".join(f"{atn.get(k, k)} from {v}" for k, v in sorted(fb.items(), key=lambda x: x[1]))
    src_note = ("Total sales, units, sessions and price come from Seller Central (2 years of history). " if m["has_sc"] else
                "Seller Central is not connected for this account, so total sales, TACoS, units, sessions, inventory and Search Query Performance are not available. ")
    notes = "".join(f"<li>{esc(n)}</li>" for n in m.get("notes", []))
    tabname = dict(NAV)
    lvl = {"high": "High", "watch": "Watch", "info": "Info"}
    al = f.get("alerts", [])
    alis = "".join(f'<li><span class="lvl"><span class="pill pill-{a["level"]}">{lvl[a["level"]]}</span></span>'
                   f'<span class="area">{esc(a["area"])}</span><span class="txt">{esc(a["text"])}</span>'
                   f'<a href="#{a["tab"]}">{esc(tabname.get(a["tab"], ""))} &rarr;</a></li>' for a in al)
    counts = {k: sum(1 for a in al if a["level"] == k) for k in lvl}
    alert_html = (f'<div class="card"><h3>Alerts This Month</h3><p class="note" style="margin:0 0 6px">{counts["high"]} high, {counts["watch"]} watch, {counts["info"]} info. '
                  f'Thresholds are fixed and apply to every account. Wasted spend and harvest use the conversion-complete window ({short_range(*m["lag"])}).</p>'
                  f'<ul class="alerts">{alis}</ul></div>') if al else '<div class="card"><h3>Alerts This Month</h3><p class="note" style="margin:0">No metric crossed an alert threshold this month.</p></div>'
    ly_note = "" if m.get("has_ly_ads") else " Ad metrics have no year-over-year comparison yet."
    return f"""
<section id="overview">
  <h2>Overview</h2>
  {alert_html}
  <p class="note">Last 30 days vs prior 30 days{' and the same 30 days last year' if m['has_sc'] else ''} (dates in the footer). Bars show the last 24 months; the orange bar is the latest complete month{' and the dashed line is the same month last year' if m['has_sc'] else ''}. Hover a bar for its value.</p>
  <div class="kpi-cards">{''.join(cards)}</div><!--chart-end-->
  <div class="card"><h3>Period Comparison</h3>{ptab}
  <p class="sub">{src_note}Advertising history: {hist}.{ly_note}</p>
  {'<ul class="trend">' + notes + '</ul>' if notes else ''}</div>
</section>"""

def tab_trends(f):
    months = f["months"]; lab = [x["month"][2:].replace("-", "/") for x in months]; has_sc = f["meta"]["has_sc"]
    tl = [_month_label(x["month"]) for x in months]
    c12 = ""
    if has_sc:
        c12 = '<div class="card chart-card"><h3>Last 24 Months: Total Sales vs Last Year, with TACoS</h3><div class="chart-wrap">' + combo_chart(
            lab, [("Total Sales (this year)", [x["total_sales"] for x in months], C_TY), ("Total Sales (last year)", [x["total_sales_ly"] for x in months], C_LY)],
            [("TACoS", [x.get("tacos") for x in months], C_LINE, None)], label_every=3, tip_labels=tl) + "</div><!--chart-end--></div>"
    c12b = combo_chart(lab, [("Ad Spend", [x.get("spend") for x in months], C_SPEND), ("Ad Sales", [x.get("ad_sales") for x in months], C_TY)],
                       [("ACoS", [x.get("acos") for x in months], C_LINE, None)], label_every=3, tip_labels=tl)
    head = [("Month", 0)] + ([("Total Sales", 1), ("Total Sales LY", 1), ("YoY", 1), ("Units", 1), ("Unit Sess %", 1)] if has_sc else []) + \
           [("Ad Spend", 1), ("Ad Sales", 1), ("ACoS", 1)] + ([("TACoS", 1)] if has_sc else []) + [("CPC", 1), ("CTR", 1), ("CVR", 1)]
    mrows = []
    for x in months:
        r = [x["month"]]
        if has_sc:
            r += [money(x["total_sales"]), money(x["total_sales_ly"]), delta(x["yoy"], "money", "up"), num(x["units"]), pct(x["unit_session"], 2)]
        r += [money(x.get("spend")), money(x.get("ad_sales")), pct(x.get("acos"))]
        if has_sc:
            r += [pct(x.get("tacos"))]
        r += [money(x.get("cpc"), 2), pct(x.get("ctr"), 2), pct(x.get("cvr"), 2)]
        mrows.append(r)
    mtab = table(head, mrows)
    wk = f["weekly"]; wl = [w["week_end"][5:].replace("-", "/") for w in wk]
    wt = [f'Week {short_range(w["week_start"], w["week_end"])}' for w in wk]
    cw = combo_chart(wl, [("Ad Spend", [w["spend"] for w in wk], C_SPEND), ("Ad Sales", [w["sales"] for w in wk], C_TY)],
                     [("ACoS", [w["acos"] for w in wk], C_LINE, None)], label_every=2, tip_labels=wt)
    cw2 = combo_chart(wl, [("Clicks", [w["clicks"] for w in wk], PAL[3])],
                      [("CTR", [w["ctr"] for w in wk], C_LINE, None), ("CVR", [w["cvr"] for w in wk], C_LINE2, "4,3")], left_fmt="int", label_every=2, tip_labels=wt)
    wrows = [[f'{w["week_start"][5:]} to {w["week_end"][5:]}', money(w["spend"]), money(w["sales"]), pct(w["acos"]), num(w["clicks"]),
              money(w["cpc"], 2), pct(w["ctr"], 2), pct(w["cvr"], 2)] for w in wk]
    wtab = table([("Week", 0), ("Spend", 1), ("Ad Sales", 1), ("ACoS", 1), ("Clicks", 1), ("CPC", 1), ("CTR", 1), ("CVR", 1)], wrows)
    return f"""
<section id="trends">
  <h2>Trends</h2>
  {c12}
  <div class="card chart-card"><h3>Last 24 Months: Ad Spend, Ad Sales, ACoS</h3><div class="chart-wrap">{c12b}</div><!--chart-end-->
  <p class="sub">Ad metrics shown from {f['meta']['ad_start_month']}, the first month of advertising data available; earlier months show "—".</p></div>
  <div class="card"><h3>Monthly Detail — 24-Month Overview</h3>{mtab}</div>
  <div class="card chart-card"><h3>Last 13 Weeks: Spend, Ad Sales, ACoS</h3><div class="chart-wrap">{cw}</div><!--chart-end--></div>
  <div class="card chart-card"><h3>Last 13 Weeks: Clicks, CTR, CVR</h3><div class="chart-wrap">{cw2}</div><!--chart-end--></div>
  <div class="card"><h3>Weekly Detail — Last 13 Weeks</h3>{wtab}</div>
</section>"""

def alloc_block(title, items, note=""):
    d = donut([(x["name"], x["l30"]["spend"]) for x in items if x["l30"]["spend"] > 0])
    rows = [[esc(x["name"]), money(x["l30"]["spend"]), pct(x["share_l30"]), pct(x["share_p30"]),
             money(x["l30"]["sales"]), pct(x["sales_share_l30"]), pct(x["l30"]["acos"]), pct(x["p30"]["acos"]),
             money(x["l30"]["cpc"], 2), pct(x["l30"]["cvr"], 2)] for x in items]
    tl = sum(x["l30"]["spend"] for x in items); ts = sum(x["l30"]["sales"] for x in items)
    rows.append(["<b>Total</b>", f"<b>{money(tl)}</b>", "100%", "100%", f"<b>{money(ts)}</b>", "100%",
                 f"<b>{pct(tl/ts if ts else None)}</b>", "", "", ""])
    t = table([("", 0), ("Spend L30", 1), ("Share L30", 1), ("Share Prior", 1), ("Ad Sales L30", 1), ("Sales Share", 1),
               ("ACoS L30", 1), ("ACoS Prior", 1), ("CPC", 1), ("CVR", 1)], rows, "data compact bucket")
    return f'<div class="card"><h3>{title}</h3><div class="donut-row single"><div class="donut-col">{d}</div><div>{t}</div></div>{note}</div>'


def tab_ad_spend(f):
    a = f["allocation"]
    return f"""
<section id="ad_spend">
  <h2>Ad Spend Allocation</h2>
  <p class="note">Last 30 days vs prior 30 days. Every ad type, match type and placement is listed, including those with no spend.</p>
  {alloc_block("By Ad Type", a["ad_type"], '<p class="sub">Sponsored Brands Video = Sponsored Brands campaigns that recorded video views.</p>')}
  {alloc_block("Sponsored Products by Match Type", a["targeting"], '<p class="sub">Product Targeting covers ASIN and category targets.</p>')}
  {alloc_block("Sponsored Products by Placement", a["placements"])}
</section>"""


def tab_strategy(f):
    sm = f["strategy_mix"]
    d = donut([(s["name"], s["spend"]) for s in sm])
    rows = [[esc(s["name"]), num(s["targets"]), money(s["spend"]), pct(s["share"]), money(s["sales"]), pct(s["sales_share"]),
             pct(s["acos"]), money(s["cpc"], 2), pct(s["cvr"], 2)] for s in sm]
    t = table([("Strategy", 0), ("Targets", 1), ("Spend", 1), ("Spend Share", 1), ("Ad Sales", 1), ("Sales Share", 1),
               ("ACoS", 1), ("CPC", 1), ("CVR", 1)], rows, "data compact bucket")
    bars = hbars([(s["name"], s["acos"]) for s in sm], color=PAL[4])
    share = "".join(f'<div class="hbar"><span class="n">{esc(s["name"])}</span><span class="t">'
                    f'<span style="width:{s["share"]*100:.1f}%;background:{PAL[0]}"></span></span><span class="v">{pct(s["share"])}</span></div>'
                    f'<div class="hbar"><span class="n"></span><span class="t"><span style="width:{s["sales_share"]*100:.1f}%;background:{PAL[2]}"></span></span>'
                    f'<span class="v">{pct(s["sales_share"])}</span></div>' for s in sm)
    return f"""
<section id="strategy">
  <h2>Strategy Mix</h2>
  <p class="note">Every Sponsored Products and Sponsored Brands target in the last 30 days, classified by what it targets: own brand terms, own ASINs, generic terms, categories, competitor terms or ASINs, and Auto.</p>
  <div class="card"><div class="donut-row single"><div class="donut-col">{d}</div><div>{t}</div></div></div>
  <div class="two-col">
    <div class="card"><h3>Spend share vs sales share</h3>
      <div class="chlegend" style="display:flex;gap:16px"><div class="lg"><span style="background:{PAL[0]}"></span>Spend share</div><div class="lg"><span style="background:{PAL[2]}"></span>Sales share</div></div>{share}</div>
    <div class="card"><h3>ACoS by strategy</h3>{bars}</div>
  </div><!--chart-end-->
</section>"""


def tab_campaigns(f):
    cs = f["campaign_summary"]; ct = f["campaign_types"]; spend = next(r["l30"] for r in f["period"]["rows"] if r["key"] == "spend")
    stats = f"""<div class="three-col">
      <div class="stat info"><div class="kc-label">Campaigns with spend (L30)</div><div class="v">{cs['with_spend_l30']}</div>
        <div class="s">{cs['enabled_now']} enabled at the end of the window · top 10 take {pct(cs['top10_share'])} of spend</div></div>
      <div class="stat warn"><div class="kc-label">Campaigns above 100% ACoS</div><div class="v">{cs['acos_over_100_n']}</div>
        <div class="s">{money(cs['acos_over_100_spend'])} spend · plus {cs['no_order_n']} with $100+ spend and no orders ({money(cs['no_order_spend'])})</div></div>
      <div class="stat"><div class="kc-label">Spend in campaigns now paused</div><div class="v">{money(cs['paused_now_spend'])}</div>
        <div class="s">{cs['paused_now_n']} campaigns spent in the window and are paused now ({pct(cs['paused_now_spend']/spend if spend else None)} of spend)</div></div></div>"""
    d = donut([(c["type"], c["spend"]) for c in ct])
    trows = [[esc(c["type"]), num(c["n"]), money(c["spend"]), pct(c["share"]), money(c["sales"]), pct(c["acos"])] for c in ct]
    tt = table([("Campaign Type", 0), ("Campaigns", 1), ("Spend L30", 1), ("Share", 1), ("Ad Sales", 1), ("ACoS", 1)], trows, "data compact bucket")
    rows, prior_only = [], []
    live = [c for c in f["campaigns"] if c["spend_l30"] > 0]
    for c in live[:f["config"]["campaign_rows"]]:
        st = '<span class="pill pill-ok">Enabled</span>' if c["status"] == "ENABLED" else '<span class="pill pill-off">Paused</span>'
        fl = " ".join(f'<span class="pill pill-flag">{esc(x)}</span>' for x in c["flags"])
        rows.append([f'<span class="trunc" title="{esc(c["name"])}" style="display:inline-block">{esc(c["name"])}</span>',
                     c["ad_type"], esc(c["type"]), st, money(c["budget"]), money(c["spend_l30"]), money(c["spend_p30"]),
                     delta(c["spend_chg"], "money", "neutral"), money(c["sales_l30"]), pct(c["acos_l30"]), pct(c["acos_p30"]), pct(c["cvr_l30"]), fl])
    for c in [c for c in f["campaigns"] if c["spend_l30"] <= 0][:40]:
        prior_only.append([f'<span class="trunc" title="{esc(c["name"])}" style="display:inline-block">{esc(c["name"])}</span>',
                           c["ad_type"], "Enabled" if c["status"] == "ENABLED" else "Paused", money(c["budget"]),
                           money(c["spend_p30"]), money(c["sales_p30"]), pct(c["acos_p30"])])
    t = table([("Campaign", 0), ("Ad", 0), ("Type", 0), ("Status", 0), ("Budget", 1), ("Spend L30", 1), ("Spend Prior", 1),
               ("Δ", 1), ("Ad Sales L30", 1), ("ACoS L30", 1), ("ACoS Prior", 1), ("CVR", 1), ("Flags", 0)], rows)
    po = table([("Campaign", 0), ("Ad", 0), ("Status Now", 0), ("Budget", 1), ("Spend Prior", 1), ("Ad Sales Prior", 1), ("ACoS Prior", 1)], prior_only)
    shown = f"Top {len(rows)} of {len(live)} by spend" if len(live) > len(rows) else "All campaigns, sorted by spend"
    return f"""
<section id="campaigns">
  <h2>Campaigns</h2>
  {stats}
  <div class="card"><h3>By Campaign Type (Last 30 Days)</h3><div class="donut-row single"><div class="donut-col">{d}</div><div>{tt}</div></div>
  <p class="sub">Type = the targeting that holds 80%+ of a campaign's spend; otherwise Mixed.</p></div>
  <div class="card"><h3>Campaigns with Spend in the Last 30 Days</h3>{t}
  <p class="sub">{shown}. Status and budget as of the last report date. Flags: no orders on $100+ spend, ACoS above 100%, and time in budget below 100% (Amazon, last 7 days).</p>
  {f'<details><summary>{cs["prior_only_n"]} campaigns spent only in the prior 30 days ({money(cs["prior_only_spend"])}) &mdash; show</summary>{po}</details>' if prior_only else ''}</div>
</section>"""

def tab_wasted(f):
    w = f["waste"]; lag = short_range(*f["meta"]["lag"])
    lc = w.get("listed_coverage")
    cov_note = (f'<p class="sub">Breakdowns and the term list cover the top {len(w["top_terms"]) if lc is None else "200"} zero-order terms by spend ({pct(lc)} of actionable waste); totals above cover every search term.</p>'
                if lc is not None and lc < 0.9 else "")
    sb = split_bar([("Converting search terms", w["converting_spend"], B.GOOD),
                    ("Zero orders, 5+ clicks (actionable)", w["actionable"], B.BAD),
                    ("Zero orders, 1–4 clicks (long tail)", w["longtail"], C_LY)])
    stats = f"""<div class="three-col">
      <div class="stat bad"><div class="kc-label">Actionable waste</div><div class="v">{money(w['actionable'])}</div>
        <div class="s">{pct(w['actionable_pct'])} of SP spend · {num(w['actionable_n'])} search terms with 5+ clicks and zero orders. Negative candidates.</div></div>
      <div class="stat"><div class="kc-label">Long-tail zero-order spend</div><div class="v">{money(w['longtail'])}</div>
        <div class="s">{pct(w['longtail_pct'])} of SP spend · {num(w['longtail_n'])} terms with 1–4 clicks. Too thin to negate one by one; controlled with bids and match type.</div></div>
      <div class="stat warn"><div class="kc-label">Zero-order targets</div><div class="v">{money(w['target_actionable'])}</div>
        <div class="s">{pct(w['target_actionable_pct'])} of SP spend · {num(w['target_actionable_n'])} of {num(w['target_count'])} keywords and targets with 5+ clicks or $5+ and zero orders. Pause candidates.</div></div></div>"""
    lab = {"AUTO": "Auto", "BROAD": "Broad", "PHRASE": "Phrase", "EXACT": "Exact", "PT": "Product targeting"}
    d1 = donut([(lab[k], v) for k, v in sorted(w["by_source"].items(), key=lambda x: -x[1])])
    d2 = donut(sorted([(k, v["spend"]) for k, v in w["by_class"].items()], key=lambda x: -x[1]))
    trows = [[esc(t["term"].upper() if t["class"] == "ASIN" else t["term"]), f'<span class="pill pill-cls">{esc(t["class"])}</span>', lab.get(t["main_source"], t["main_source"]),
              money(t["spend"]), num(t["clicks"]), num(t["impressions"]), num(t["campaigns"])] for t in w["top_terms"]]
    tt = table([("Search Term", 0), ("Type", 0), ("Main Source", 0), ("Spend", 1), ("Clicks", 1), ("Impr.", 1), ("Campaigns", 1)], trows)
    grows = [[esc(t["target"]), esc(t["type"].title() if t["type"] != "ASIN" else "ASIN"),
              f'<span class="trunc" style="display:inline-block" title="{esc(t["campaign"])}">{esc(t["campaign"])}</span>',
              money(t["spend"]), num(t["clicks"]), num(t["impressions"])] for t in w["top_targets"]]
    gt = table([("Keyword / Target", 0), ("Type", 0), ("Campaign", 0), ("Spend", 1), ("Clicks", 1), ("Impr.", 1)], grows)
    return f"""
<section id="wasted">
  <h2>Wasted Spend</h2>
  <p class="note">Conversion-complete window: {lag}, the 30 days ending 14 days before the report date, so every click has had its full 14-day attribution window. Recent clicks that may still convert are not counted as waste.</p>
  <div class="card"><h3>Where Sponsored Products spend went ({lag})</h3>{sb}
  <p class="sub">Search-term level, {num(w['term_count'])} search terms, {money(w['sp_spend_l30'])} SP spend. Zero orders means no 14-day attributed purchase.</p><!--chart-end--></div>
  {stats}
  <div class="donut-row">
    <div class="donut-col"><h4>Actionable waste by source</h4>{d1}</div>
    <div class="donut-col"><h4>Actionable waste by query type</h4>{d2}</div>
  </div>{cov_note}<!--chart-end-->
  <div class="card"><h3>Top zero-order search terms (5+ clicks)</h3>{tt}
  <p class="sub">Own-brand terms with zero orders point to a listing or stock issue, not a negative. ASIN terms are negated as product targets.</p></div>
  <div class="card"><h3>Top zero-order keywords and targets</h3>{gt}</div>
</section>"""


def tab_harvest(f):
    h = f["harvest"]; sq = h["sqp"]; tiers = h["tiers"]; lag = short_range(*f["meta"]["lag"])
    stats = f"""<div class="kpi-grid">
      <div class="kpi"><div class="kpi-label">Converting terms not on Exact / ASIN</div><div class="kpi-value">{h['n']}</div><div class="kpi-meta">{money(h['sales'])} sales · {pct(h['sales_share_of_sp'])} of SP sales ({lag})</div></div>
      <div class="kpi"><div class="kpi-label">PRIME / STRONG / WATCH</div><div class="kpi-value">{tiers.get('PRIME',{}).get('n',0)} / {tiers.get('STRONG',{}).get('n',0)} / {tiers.get('WATCH',{}).get('n',0)}</div><div class="kpi-meta">PRIME sales {money(tiers.get('PRIME',{}).get('sales',0))}</div></div>
      <div class="kpi"><div class="kpi-label">Exact share of SP spend</div><div class="kpi-value">{pct(h['exact_spend_share'])}</div><div class="kpi-meta">last 30 days · prior 30 days {pct(h['exact_spend_share_p30'])}</div></div>
      <div class="kpi"><div class="kpi-label">Exact ACoS / sales share</div><div class="kpi-value">{pct(h['exact_acos'])}</div><div class="kpi-meta">{pct(h['exact_sales_share'])} of SP sales</div></div></div>"""
    rows = [[esc(r["term"].upper() if r["class"] == "ASIN" else r["term"]), f'<span class="pill pill-{r["tier"]}">{r["tier"]}</span>',
             f'<span class="pill pill-cls">{esc(r["class"])}</span>', ", ".join(x.title() for x in r["sources"]), money(r["sales"]),
             num(r["orders"]), num(r["clicks"]), money(r["spend"]), pct(r["acos"]), pct(r["cvr"]), money(r["cpc"], 2), r["action"]] for r in h["rows"]]
    t = table([("Search Term", 0), ("Tier", 0), ("Type", 0), ("Converting From", 0), ("Sales", 1), ("Orders", 1), ("Clicks", 1),
               ("Spend", 1), ("ACoS", 1), ("CVR", 1), ("CPC", 1), ("Add As", 0)], rows)
    sqp_html = '<div class="card"><h3>Search Query Performance</h3><p class="sub">Not available: Seller Central (Brand Analytics) is not connected for this account.</p></div>'
    if sq:
        cov_cls = {"Exact": "pill-ok", "Phrase": "pill-STRONG", "Broad": "pill-STRONG", "None": "pill-flag"}
        srows = [[esc(x["query"]), num(x["volume"]), num(x["market_purchases"]), num(x["brand_purchases"]), pct(x["purchase_share"], 2),
                  pct(x["click_share"], 2), pct(x["impr_share"], 2), f'<span class="pill {cov_cls[x["keyword_coverage"]]}">{x["keyword_coverage"]}</span>',
                  money(x["paid_spend_l30"]), num(x["paid_orders_l30"])] for x in sq["top_generic"]]
        stab = table([("Search Query", 0), ("Search Volume", 1), ("Market Purchases", 1), ("Brand Purchases", 1), ("Purchase Share", 1),
                      ("Click Share", 1), ("Impr. Share", 1), ("Keyword Coverage", 0), ("Ad Spend", 1), ("Ad Orders", 1)], srows)
        cc = sq["coverage_counts"]
        sqp_html = f"""<div class="card"><h3>Search Query Performance: top non-branded queries by market purchases</h3>
  <p class="note" style="margin:0 0 10px">Brand Analytics, 4 weeks ending {sq['window'][1]}. Of the top 50 non-branded queries: {cc['Exact']} on Exact, {cc['Phrase']} reached by Phrase, {cc['Broad']} by Broad, {cc['None']} with no keyword coverage ({num(sq['uncovered_generic_purchases'])} market purchases).</p>
  {stab}
  <p class="sub">Keyword coverage checks the account's Exact, Phrase and Broad keywords that served in the last 30 days. Ad spend and orders are the search-term report for the same query in the conversion-complete window ({lag}).</p></div>"""
    return f"""
<section id="harvest">
  <h2>Harvest</h2>
  {stats}
  <div class="card"><h3>Converting search terms not yet on Exact keywords or ASIN targets ({lag})</h3>{t}
  <p class="sub">Minimum 2 orders. PRIME: 30+ clicks and ACoS ≤ 40%. STRONG: ACoS ≤ 60%. WATCH: converting above 60% ACoS. Top 1,000 search terms by spend are scanned.</p></div>
  {sqp_html}
</section>"""

def tab_products(f):
    ps = f["product_summary"]
    rows = [[f'{esc(p["name"] or p["asin"])}<div class="sub">{p["asin"]}</div>', money(p["spend_l30"]), pct(p["share"]),
             money(p["ad_sales_l30"]), delta((p["ad_sales_l30"] - p["ad_sales_p30"]) / p["ad_sales_p30"] if p["ad_sales_p30"] else None, "money", "up"),
             f'{pct(p["acos_p30"])} → {pct(p["acos_l30"])}', f'{pct(p["cvr_p30"])} → {pct(p["cvr_l30"])}',
             money(p["total_sales_l30"]), f'{money(p["asp_p30"],2)} → {money(p["asp_l30"],2)}' if p["asp_l30"] else "—",
             f'{pct(p["us_p30"])} → {pct(p["us_l30"])}' if p["us_l30"] else "—", num(p["available"]), esc(p["health"] or "—")] for p in f["products"]]
    t = table([("Advertised Product", 0), ("Ad Spend", 1), ("Share", 1), ("Ad Sales", 1), ("vs Prior", 1), ("ACoS", 1), ("Ad CVR", 1),
               ("Total Sales", 1), ("Avg Price", 1), ("Unit Sess %", 1), ("FBA Avail.", 1), ("Stock", 0)], rows)
    inv_html = '<div class="card"><h3>FBA Inventory</h3><p class="sub">Not available: Seller Central is not connected for this account.</p></div>'
    if f["inventory"]:
        isum = f["inventory_summary"]
        irows = []
        for i in f["inventory"]:
            hc = "pill-flag" if i["health"] in ("Out of stock", "Low stock") else "pill-ok"
            irows.append([f'{esc(i["name"])}<div class="sub">{i["asin"]}</div>', num(i["available"]), num(i["inbound"]), num(i["reserved"]),
                          num(i["units_t30"]), num(i["units_t7"]), "—" if i["weeks_cover"] is None else f'{i["weeks_cover"]:.1f}',
                          f'<span class="pill {hc}">{esc(i["health"])}</span>', esc(i["alert"]),
                          f'{num(i["ship_in_qty"])} by {i["ship_in_date"]}' if i["ship_in_qty"] else "—"])
        it = table([("Product", 0), ("Available", 1), ("Inbound", 1), ("Reserved", 1), ("Units 30d", 1), ("Units 7d", 1),
                    ("Weeks of Cover", 1), ("Health", 0), ("Amazon Alert", 0), ("Amazon Ship-in Rec.", 0)], irows)
        inv_html = f"""<div class="three-col">
      <div class="stat {'bad' if isum['out_of_stock_selling'] else 'good'}"><div class="kc-label">Selling SKUs out of stock</div><div class="v">{isum['out_of_stock_selling']}</div><div class="s">SKUs with units shipped in 30 days and 0 available</div></div>
      <div class="stat {'warn' if isum['under_4_weeks'] else 'good'}"><div class="kc-label">Under 4 weeks of cover</div><div class="v">{isum['under_4_weeks']}</div><div class="s">Available + inbound vs last-30-day velocity</div></div>
      <div class="stat info"><div class="kc-label">FBA units available / inbound</div><div class="v">{num(isum['available_units'])}</div><div class="s">{num(isum['inbound_units'])} inbound · {isum['skus_tracked']} SKUs tracked</div></div></div>
  <div class="card"><h3>FBA Inventory: top selling SKUs (snapshot {f['meta']['report_date']})</h3>{it}
  <p class="sub">Weeks of cover = (available + inbound) ÷ average weekly units shipped over the last 30 days. Ship-in recommendation is Amazon's.</p></div>"""
    return f"""
<section id="products">
  <h2>Products & Inventory</h2>
  <div class="card"><h3>Top Advertised Products (Last 30 Days vs Prior 30 Days)</h3>{t}
  <p class="sub">{ps['advertised_asins']} advertised ASINs; the top 5 take {pct(ps['top5_share'])} of Sponsored Products spend.</p></div>
  {inv_html}
</section>"""

def tab_budgets(f):
    b = f["budgets"]; q = f["q4"]
    if b["constrained"]:
        rows = [[f'<span class="trunc" style="display:inline-block" title="{esc(c["campaign"])}">{esc(c["campaign"])}</span>',
                 money(c["budget"]), money(c["suggested"]), pct(c["tib"], 0), f'{num(c["missed_clicks_lo"])}–{num(c["missed_clicks_hi"])}',
                 f'{money(c["missed_sales_lo"])}–{money(c["missed_sales_hi"])}'] for c in b["constrained"]]
        t = table([("Campaign", 0), ("Daily Budget", 1), ("Amazon Suggested", 1), ("Time in Budget", 1), ("Est. Missed Clicks", 1), ("Est. Missed Sales", 1)], rows)
        intro = f"{len(b['constrained'])} of the top {b['checked']} enabled Sponsored Products campaigns were out of budget part of the week. Amazon estimates {money(b['missed_sales_lo'])}–{money(b['missed_sales_hi'])} in missed sales across them."
    else:
        t = ""; intro = f"None of the top {b['checked']} enabled Sponsored Products campaigns ran out of budget in the week checked."
    q4_html = '<div class="card"><h3>Q4 Readiness</h3><p class="sub">Last-year sales history needs Seller Central, which is not connected for this account.</p></div>'
    if q:
        ly = q["ly_weekly"]
        c = combo_chart([w["wk"][5:].replace("-", "/") for w in ly], [("Total Sales LY", [w["total_sales"] for w in ly], C_TY)], [], label_every=2,
                        tip_labels=[f'Week of {dt.date.fromisoformat(w["wk"]).strftime("%b %-d, %Y")}' for w in ly])
        days = table([("Day", 0), ("Total Sales", 1), ("Units", 1)], [[d["date"], money(d["total_sales"]), num(d["units"])] for d in q["ly_top_days"]])
        q4_html = f"""<div class="three-col">
    <div class="stat info"><div class="kc-label">Nov–Dec {q['year']} total sales</div><div class="v">{money(q['ly_nov_dec_sales'])}</div>
      <div class="s">{pct(q['ly_nov_dec_share_of_2025'])} of {q['year']} total sales ({money(q['ly_2025_sales'])})</div></div>
    <div class="stat info"><div class="kc-label">Nov–Dec {q['year']} units</div><div class="v">{num(q['ly_nov_dec_units'])}</div><div class="s">All ASINs, Seller Central ordered units</div></div>
    <div class="stat warn"><div class="kc-label">FBA units available now</div><div class="v">{num(q['available_units_now'])}</div>
      <div class="s">All tracked SKUs, plus {num(q['inbound_units_now'])} inbound (snapshot {f['meta']['report_date']})</div></div></div>
  <div class="card chart-card"><h3>Last Year: weekly total sales, Oct–Dec {q['year']}</h3><div class="chart-wrap">{c}</div><!--chart-end--></div>
  <div class="card"><h3>Last Year: top sales days in Q4</h3>{days}
  <p class="sub">Confirm this year's event dates and FBA inbound cutoffs in Seller Central.</p></div>"""
    return f"""
<section id="budgets">
  <h2>Budgets & Q4 Readiness</h2>
  <div class="card"><h3>Budget-constrained campaigns ({b['window'] or 'n/a'})</h3>
  <p class="note" style="margin:0 0 10px">{intro}</p>{t}</div>
  {q4_html}
</section>"""

def build(findings, out, logo):
    f = json.load(open(findings)); m = f["meta"]
    lb = load_logo_b64(logo)
    logo_html = f'<img src="data:image/png;base64,{lb}" alt="{B.LOGO_ALT}"/>' if lb else ""
    nav = "".join(f'<li><a href="#{k}">{v}</a></li>' for k, v in NAV)
    tabs = [tab_overview, tab_trends, tab_ad_spend, tab_strategy, tab_campaigns, tab_wasted, tab_harvest, tab_products, tab_budgets]
    body = "".join(add_source_captions(t(f), m["has_sc"]) for t in tabs)
    dl = [("Last 30 days", drange(*m["l30"])), ("Prior 30 days", drange(*m["p30"]))]
    if m["has_sc"] or m.get("has_ly_ads"):
        dl.append(("Same period last year", drange(*m["ly"])))
    dl.append(("Wasted spend & harvest (conversion-complete)", drange(*m["lag"])))
    dl.append(("Budget check (Amazon, 7 days)", f["budgets"]["window"] or "n/a"))
    dates = "".join(f"<div><b>{esc(k)}:</b> {esc(v)}</div>" for k, v in dl)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m['display_brand'])} — Monthly Account Review</title>
<style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
<header class="hero"><div class="hero-inner"><div class="hero-brand">{logo_html}
<div class="hero-title"><strong>{B.REPORT_TITLE_PREFIX}</strong> &middot; Monthly Account Review &middot; {esc(m['display_brand'])}</div></div>
<div class="hero-meta"><div>Marketplace: {esc(m['marketplace'])}</div>
<div>Report Created: {m['report_date']}</div><div>Internal &middot; Account Team</div></div></div></header>
<nav class="tabs"><ul>{nav}</ul></nav>
<main>{body}</main>
<footer><div class="foot-dates">{dates}</div><div class="disclaimer">{B.DISCLAIMER}</div>
<div style="margin-top:10px;opacity:0.6;">{B.BRAND_NAME} &middot; {esc(m['display_brand'])} &middot; {m['report_date']}</div></footer>
</body></html>"""
    open(out, "w").write(doc)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--logo", default=B.LOGO_HERO)
    a = ap.parse_args()
    print("[done]", build(a.findings, a.out, a.logo))
