#!/usr/bin/env python3
"""Build the four AMC pages (new-to-brand, repeat-purchase, path-to-conversion, time-to-conversion) for one account from amc_findings.json.

Second page inside the account's Monthly Audit link: same XP header, links bar, Pages
switcher, palette and footer as the monthly review (imports build_account_review helpers).
Internal, data-only page for account managers: trends and numbers, no recommendations.

Usage:
    python3 tools/build_amc_insights.py --findings amc_findings.json --out accounts/<slug>/amc.html
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_account_review as R                     # noqa: E402  (charts, tables, brand, header)
from build_account_review import B, H, esc, money, pct, num, table, hbars, combo_chart, _CHART_JS  # noqa: E402

PAL = B.CATEGORY_PALETTE
C_SP, C_SB, C_SD = PAL[2], PAL[0], PAL[3]
C_SNS, C_REP, C_ONE = PAL[0], PAL[2], PAL[8]
PATH_COLORS = [PAL[2], PAL[0], PAL[1], PAL[3], PAL[5], PAL[6], PAL[8]]

NAV = [("overview", "Overview"), ("ntb", "New-to-Brand"), ("ntb_terms", "NTB Search Terms"),
       ("repeat", "Repeat & SnS"), ("path", "Path to Conversion"), ("ttc", "Time to Conversion")]
SOURCES = {
    "overview": "Amazon Marketing Cloud (Sponsored Ads attributed events and conversions)",
    "ntb": "Amazon Marketing Cloud attributed events and Sponsored Ads traffic",
    "ntb_terms": "Amazon Marketing Cloud attributed events joined to Sponsored Ads search term clicks",
    "repeat": "Amazon Marketing Cloud conversions (orders and Subscribe & Save sign-ups)",
    "path": "Amazon Marketing Cloud conversions and Sponsored Ads traffic",
    "ttc": "Amazon Marketing Cloud attributed events (click-attributed purchases)",
}
AD = {"sponsored_products": "Sponsored Products", "sponsored_brands": "Sponsored Brands", "sponsored_display": "Sponsored Display"}
SHORT = {"sponsored_products": "SP", "sponsored_brands": "SB", "sponsored_display": "SD"}

CSS = """
.amc-kpis { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin: 6px 0 22px; }
@media (max-width: 900px) { .amc-kpis { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 520px) { .amc-kpis { grid-template-columns: 1fr; } }
.amc-k { background:#fff; border:1px solid %(border)s; border-radius:6px; padding:14px; }
.amc-k .l { font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:%(muted)s; }
.amc-k .v { font-size:24px; font-weight:600; color:%(dark)s; margin-top:4px; }
.amc-k .s { font-size:12px; color:%(muted)s; margin-top:2px; }
.amc-reads { background:#fff; border:1px solid %(border)s; border-left:4px solid %(accent)s; border-radius:6px;
             padding:14px 18px; margin: 4px 0 22px; }
.amc-reads h4 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:%(muted)s; margin-bottom:8px; }
.amc-reads li { margin: 4px 0 4px 18px; font-size:14px; }
.amc-note { font-size:12.5px; color:%(muted)s; margin: 6px 0 14px; }
.amc-grid2 { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap:22px; }
.amc-grid2 > div { min-width:0; }
@media (max-width: 900px) { .amc-grid2 { grid-template-columns: minmax(0,1fr); } }
.mini-split { display:flex; height:10px; width:120px; border-radius:2px; overflow:hidden; background:#eee; }
.mini-split span { display:block; height:100%%; }
""" % dict(border=B.BORDER, muted=B.MUTED, dark=B.DARK, accent=B.ACCENT)


# ------------------------------------------------------------------ helpers --
def sdiv(a, b):
    return (a / b) if (a is not None and b) else None


def captions(section_html, sid):
    """'Source: ...' after every table and chart group (QA rule shared with the monthly review)."""
    R.SECTION_SOURCES[sid] = SOURCES[sid]
    return R.add_source_captions(section_html, True)


def section(sid, title, intro, body):
    return captions(f'<section id="{sid}"><h2>{esc(title)}</h2><p class="amc-note">{intro}</p>{body}</section>', sid)


def reads(items):
    items = [i for i in items if i]
    if not items:
        return ""
    return '<div class="amc-reads"><h4>What the data shows</h4><ul>' + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"


def kpi(label, value, sub=""):
    return f'<div class="amc-k"><div class="l">{esc(label)}</div><div class="v">{value}</div><div class="s">{sub}</div></div>'


def stacked_chart(labels, series, line=None, w=780, h=280, share=False, left_fmt="int"):
    """Stacked monthly bars (optionally 100%% share) with an optional right-axis % line.
    series: [(name, values, color)]; line: (name, values, color). Hover tooltip like combo_chart."""
    n = len(labels); pl, pr, pt, pb = 62, 56 if line else 16, 18, 34
    pw, ph = w - pl - pr, h - pt - pb
    totals = [sum((s[1][i] or 0) for s in series) for i in range(n)]
    smax = 1.0 if share else (max(totals + [1]))
    lf = (lambda v: money(v)) if left_fmt == "money" else num
    o = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">']
    lmax = (max([v or 0 for v in line[1]] + [0.0001]) * 1.15) if line else 1
    for gy in range(5):
        y = pt + ph * gy / 4
        o.append(f'<line x1="{pl}" y1="{y:.0f}" x2="{w-pr}" y2="{y:.0f}" stroke="#eee"/>')
        lv = smax * (1 - gy / 4)
        if share:
            lt = f"{lv*100:.0f}%"
        elif left_fmt == "money":
            lt = f"${lv/1000:,.0f}K" if smax >= 5000 else f"${lv:,.0f}"
        else:
            lt = f"{lv/1000:,.1f}K" if smax >= 5000 else f"{lv:,.0f}"
        o.append(f'<text x="{pl-6}" y="{y+3:.0f}" font-size="10" fill="#999" text-anchor="end">{lt}</text>')
        if line:
            o.append(f'<text x="{w-pr+6}" y="{y+3:.0f}" font-size="10" fill="#999">{lmax*(1-gy/4)*100:.0f}%</text>')
    xs = [pl + pw * (i + 0.5) / n for i in range(n)]
    bw = pw / n * 0.62
    for i in range(n):
        base = pt + ph
        for _, vals, col in series:
            v = vals[i] or 0
            v = (v / totals[i]) if (share and totals[i]) else v
            bh = ph * v / smax
            if bh > 0:
                o.append(f'<rect x="{xs[i]-bw/2:.1f}" y="{base-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{col}"/>')
            base -= bh
        o.append(f'<text x="{xs[i]:.0f}" y="{h-10}" font-size="10" fill="#999" text-anchor="middle">{esc(labels[i])}</text>')
    ly = lambda v: pt + ph * (1 - (v or 0) / lmax)
    if line:
        pts = [f"{xs[i]:.0f},{ly(v):.0f}" for i, v in enumerate(line[1]) if v is not None]
        o.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{line[2]}" stroke-width="2.4"/>')
        for p_ in pts:
            x, y = p_.split(",")
            o.append(f'<circle cx="{x}" cy="{y}" r="2.6" style="fill:{line[2]}"/>')
    o.append(f'<line class="xpc-guide" x1="0" y1="{pt}" x2="0" y2="{pt+ph}" stroke="#bbb" stroke-dasharray="3,3" style="display:none"/>')
    tips = []
    for i in range(n):
        dots = (f'<circle cx="{xs[i]:.0f}" cy="{ly(line[1][i]):.0f}" r="4.2" style="fill:{line[2]}"/>'
                if line and line[1][i] is not None else "")
        o.append(f'<g class="xpc-dots" data-i="{i}" style="display:none">{dots}</g>')
        rows = []
        for nm, vals, col in reversed(series):
            v = vals[i]
            sh = f" ({v/totals[i]*100:.0f}%)" if (v is not None and totals[i]) else ""
            rows.append([nm, (lf(v) if v is not None else "—") + sh, col])
        if line:
            rows.append([line[0], pct(line[1][i]), line[2]])
        tips.append({"m": esc(labels[i]), "x": round(xs[i], 1), "rows": rows})
    cw = pw / n
    for i in range(n):
        o.append(f'<rect class="xpc-hit" data-i="{i}" x="{pl + cw*i:.1f}" y="{pt}" width="{cw:.1f}" height="{ph}" fill="transparent"/>')
    o.append("</svg>")
    leg = "".join(f'<div class="lg"><span style="background:{c}"></span>{esc(nm)}</div>' for nm, _, c in series)
    if line:
        leg += f'<div class="lg"><span style="background:{line[2]}"></span>{esc(line[0])}</div>'
    data_attr = esc(json.dumps({"w": w, "tips": tips}))
    return (f'<div class="chlegend">{leg}</div><div class="xpc" data-chart="{data_attr}">' + "".join(o)
            + '<div class="xpc-tip" role="tooltip"></div></div>' + _CHART_JS + "<!--chart-end-->")


def chart(html):
    return html + ("" if html.endswith("<!--chart-end-->") else "<!--chart-end-->")


def mini_split(parts):
    tot = sum(v for _, v, _ in parts) or 1
    return '<span class="mini-split">' + "".join(
        f'<span style="width:{v/tot*100:.1f}%;background:{c}" title="{esc(n)} {v/tot*100:.0f}%"></span>' for n, v, c in parts) + "</span>"


def chg(a, b):
    return f"{a:,.0f} → {b:,.0f}"


# ------------------------------------------------------------------ tabs ----
def tab_ntb(f):
    L, N = f["months"], f["ntb"]
    ntb_pct = [sdiv(a, b) for a, b in zip(N["ntb_purchases"], N["purchases"])]
    cpa = [sdiv(s, n) for s, n in zip(N["spend"], N["ntb_purchases"])]
    other = [max((t or 0) - (a or 0) - (b or 0), 0) for t, a, b in zip(N["ntb_purchases"], N["sp_ntb"], N["sb_ntb"])]
    ch1 = stacked_chart(L, [("Sponsored Products", N["sp_ntb"], C_SP), ("Sponsored Brands", N["sb_ntb"], C_SB),
                            ("Other / below privacy floor", other, C_SD)],
                        line=("NTB % of ad orders", ntb_pct, B.ACCENT))
    ch2 = chart(combo_chart(L, [("Ad spend", N["spend"], PAL[8])], [("Spend per NTB order", cpa, B.ACCENT, "")],
                            right_fmt="money"))
    rows = []
    for i, lab in enumerate(L):
        rows.append([lab, money(N["spend"][i]), num(N["customers"][i]), num(N["ntb_customers"][i]),
                     pct(sdiv(N["ntb_customers"][i], N["customers"][i])), num(N["purchases"][i]), num(N["ntb_purchases"][i]),
                     pct(ntb_pct[i]), money(N["ntb_sales"][i]), money(cpa[i]), num(N["sp_ntb"][i]), num(N["sb_ntb"][i]),
                     pct(sdiv(N["sp_ntb"][i], N["ntb_purchases"][i]))])
    tb = table([("Month", 0), ("Ad spend", 1), ("Customers", 1), ("NTB customers", 1), ("NTB customer %", 1), ("Orders", 1),
                ("NTB orders", 1), ("NTB order %", 1), ("NTB sales", 1), ("Spend per NTB order", 1), ("SP NTB", 1),
                ("SB NTB", 1), ("SP share of NTB", 1)], rows)
    hi = max(range(len(L)), key=lambda i: N["ntb_purchases"][i] or 0)
    lo = min(range(len(L)), key=lambda i: cpa[i] or 1e9)
    sp_sh = sdiv(sum(N["sp_ntb"]), sum(N["ntb_purchases"]))
    rd = reads([f"NTB orders peaked in {esc(L[hi])} at {num(N['ntb_purchases'][hi])}; {esc(L[-1])} closed at {num(N['ntb_purchases'][-1])}.",
                f"Spend per NTB order ranged from {money(min(c for c in cpa if c))} ({esc(L[lo])}) to {money(max(c for c in cpa if c))}.",
                f"Sponsored Products carried {pct(sp_sh)} of NTB orders across the period. The Ads console reports NTB for SB and SD only."])
    return section("ntb", "New-to-Brand", "Ad-attributed purchases by shoppers who had not bought the brand in the prior 12 months, "
                   "booked on conversion date.",
                   rd + "<h3>NTB orders by ad type and NTB share of ad orders</h3>" + ch1
                   + "<h3>Ad spend and spend per NTB order</h3>" + ch2 + "<h3>Monthly detail</h3>" + tb)


def tab_terms(f):
    S = f["search_terms"]
    cls = S["classes"]; tot = sum(c["ntb"] for c in cls) + S["suppressed"]["ntb"]
    bars = hbars([(c["name"], sdiv(c["ntb"], tot)) for c in cls] + [("Below privacy floor", sdiv(S["suppressed"]["ntb"], tot))],
                 color=C_SP)
    rows = [[esc(c["name"]), num(c["ntb"]), pct(sdiv(c["ntb"], tot)), money(c["ntb_sales"]), money(c["spend"]),
             money(sdiv(c["spend"], c["ntb"])), f'{(sdiv(c["ntb"], c["clicks"]) or 0)*100:.1f}'] for c in cls]
    sp_ = S["suppressed"]
    rows.append(["Below privacy floor", num(sp_["ntb"]), pct(sdiv(sp_["ntb"], tot)), money(sp_["ntb_sales"]), money(sp_["spend"]),
                 money(sdiv(sp_["spend"], sp_["ntb"])), "—"])
    t1 = table([("Term type", 0), ("NTB orders", 1), ("Share", 1), ("NTB sales", 1), ("Term spend", 1), ("Spend per NTB order", 1),
                ("NTB per 100 clicks", 1)], rows)
    trs = [[esc(t["term"]), SHORT.get(t["ad"], t["ad"]), esc(t["class"]), num(t["ntb"]), money(t["ntb_sales"]), num(t["clicks"]),
            money(t["spend"]), money(sdiv(t["spend"], t["ntb"]))] for t in S["top"]]
    t2 = table([("Search term", 0), ("Ad", 0), ("Type", 0), ("NTB orders", 1), ("NTB sales", 1), ("Clicks", 1), ("Term spend", 1),
                ("Spend per NTB order", 1)], trs)
    gen = [c for c in cls if c["name"] == "Generic"]
    br = [c for c in cls if c["name"] == "Branded"]
    rd = reads([f"Branded searches brought {pct(sdiv(br[0]['ntb'], tot))} of NTB orders at {money(sdiv(br[0]['spend'], br[0]['ntb']))} per NTB order." if br else "",
                f"Generic searches brought {pct(sdiv(gen[0]['ntb'], tot))} at {money(sdiv(gen[0]['spend'], gen[0]['ntb']))} per NTB order." if gen else "",
                f"{pct(sdiv(sp_['ntb'], tot))} of NTB orders sit on terms below the 100-shopper privacy floor and are not attributed to a term."])
    return section("ntb_terms", "NTB Search Terms",
                   f"NTB shoppers who clicked the term in the same campaign within 14 days before their NTB purchase, {esc(S['window'])}. "
                   "A shopper who clicked two terms counts for both. Term spend is all spend on the term.",
                   rd + '<div class="amc-grid2"><div><h3>Share of NTB orders by term type</h3>' + bars + "<!--chart-end--></div><div>"
                   + "<h3>Term type summary</h3>" + t1 + "</div></div>" + f"<h3>Top {len(S['top'])} terms by NTB orders</h3>" + t2)


def tab_repeat(f):
    L, Rp = f["months"], f["repeat"]
    sns_sh = [sdiv(a, b) for a, b in zip(Rp["sns_sales"], Rp["sales"])]
    has_sns = sum(v or 0 for v in Rp["signups"]) > 0 or sum(v or 0 for v in Rp["sns_sales"]) > 0
    rep_sh = [sdiv(a, b) for a, b in zip(Rp["repeat_sales"], Rp["sales"])]
    segs = [("One-time buyers", Rp["one_sales"], C_ONE), ("Repeat" + (" (non-SnS)" if has_sns else ""), Rp["repeat_sales"], C_REP)]
    if has_sns:
        segs.append(("SnS subscribers", Rp["sns_sales"], C_SNS))
    ch1 = stacked_chart(L, segs, line=None, share=True, left_fmt="money")
    if has_sns:
        ch2 = ("<h3>SnS sign-ups and SnS share of sales</h3>"
               + chart(combo_chart(L, [("SnS sign-ups", Rp["signups"], C_SNS)], [("SnS share of sales", sns_sh, B.ACCENT, "")], left_fmt="int")))
    else:
        ch2 = ("<h3>Repeat customers and repeat share of sales</h3>"
               + chart(combo_chart(L, [("Repeat customers", Rp["repeat_customers"], C_REP)], [("Repeat share of sales", rep_sh, B.ACCENT, "")], left_fmt="int")))
    rows = []
    for i, lab in enumerate(L):
        rows.append([lab, num(Rp["customers"][i]), money(Rp["sales"][i]), num(Rp["sns_customers"][i]), pct(sns_sh[i]),
                     num(Rp["repeat_customers"][i]), pct(sdiv(Rp["repeat_sales"][i], Rp["sales"][i])),
                     num(Rp["one_customers"][i]), pct(sdiv(Rp["one_sales"][i], Rp["sales"][i])), num(Rp["signups"][i])])
    tb = table([("Month", 0), ("Customers", 1), ("Sales", 1), ("SnS customers", 1), ("SnS % sales", 1), ("Repeat customers", 1),
                ("Repeat % sales", 1), ("One-time customers", 1), ("One-time % sales", 1), ("SnS sign-ups", 1)], rows)
    A = f["asin"]; atot = sum(a["sales"] for a in A) or 1
    arows = []
    for a in A:
        arows.append([esc(a["asin"]), esc(a["name"]), money(a["sales"]), pct(a["sales"] / atot), num(a["customers"]),
                      mini_split([("SnS", a["sns_sales"], C_SNS), ("Repeat", a["repeat_sales"], C_REP), ("One-time", a["one_sales"], C_ONE)]),
                      pct(sdiv(a["sns_sales"], a["sales"])), pct(sdiv(a["repeat_sales"], a["sales"])), pct(sdiv(a["one_sales"], a["sales"])),
                      f'{(sdiv(a["orders"], a["customers"]) or 0):.2f}'])
    head = [("ASIN", 0), ("Product", 0), ("Sales", 1), ("Share", 1), ("Customers", 1), ("Mix", 0), ("SnS %", 1), ("Repeat %", 1),
            ("One-time %", 1), ("Orders / customer", 1)]
    if not has_sns:
        head = head[:6] + head[7:]; arows = [r[:6] + r[7:] for r in arows]
    ta = table(head, arows)
    big_one = max(A, key=lambda a: a["one_sales"]) if A else None
    rd = reads([(f"SnS share of sales moved from {pct(sns_sh[0])} in {esc(L[0])} to {pct(sns_sh[-1])} in {esc(L[-1])}." if has_sns
                 else "No Subscribe & Save sign-ups or subscriber orders in the window."),
                f"Repeat buyers moved from {pct(rep_sh[0])} to {pct(rep_sh[-1])} of sales ({esc(L[0])} → {esc(L[-1])}).",
                f"One-time buyers moved from {pct(sdiv(Rp['one_sales'][0], Rp['sales'][0]))} to {pct(sdiv(Rp['one_sales'][-1], Rp['sales'][-1]))} of sales.",
                (f"SnS sign-ups: {chg(Rp['signups'][0] or 0, Rp['signups'][-1] or 0)} per month ({esc(L[0])} → {esc(L[-1])})." if has_sns else ""),
                (f"Largest one-time base: {esc(big_one['name'] or big_one['asin'])}, {pct(sdiv(big_one['one_sales'], big_one['sales']))} of its sales from one-time buyers."
                 if big_one else "")])
    return section("repeat", "Repeat Purchase & Subscribe & Save",
                   "Each customer-month is one segment: SnS subscriber (signed up by that month) → repeat (bought earlier or 2+ orders "
                   "that month) → one-time. Segments add up to the total. Covers all orders on tracked ASINs that AMC can see.",
                   rd + "<h3>Sales mix by customer type</h3>" + ch1 + ch2
                   + "<h3>Monthly detail</h3>" + tb + f"<h3>By ASIN ({esc(f['repeat_window'])})</h3>" + ta)


def tab_path(f):
    L, P = f["months"], f["path"]
    names = P["order"]
    series = [(nm, P["paths"][nm]["buyers"], PATH_COLORS[k % len(PATH_COLORS)]) for k, nm in enumerate(names)]
    ch1 = stacked_chart(L, series, share=True)
    ch2 = stacked_chart(L, series, share=False)
    rows = []
    for nm in names:
        d = P["paths"][nm]; b = sum(v or 0 for v in d["buyers"]); s = sum(v or 0 for v in d["sales"])
        wt = lambda key: sdiv(sum((d[key][i] or 0) * (d["buyers"][i] or 0) for i in range(len(L))), b)
        rows.append([esc(nm), num(b), pct(sdiv(b, P["total_touched"])), money(s), money(sdiv(s, b)),
                     f'{(wt("touch_days") or 0):.1f}', f'{(wt("days_to_order") or 0):.1f}', pct(sdiv(sum(d["clicked"]), b))])
    tb = table([("Ad types seen (30 days before purchase)", 0), ("Buyers", 1), ("Share", 1), ("Sales", 1), ("Sales per buyer", 1),
                ("Avg touch days", 1), ("Avg days first touch → order", 1), ("Buyers who clicked", 1)], rows)
    mrows = []
    for i, lab in enumerate(L):
        tot = sum((P["paths"][nm]["buyers"][i] or 0) for nm in names)
        mrows.append([lab, num(tot)] + [pct(sdiv(P["paths"][nm]["buyers"][i], tot)) for nm in names])
    tm = table([("Month", 0), ("Ad-touched buyers", 1)] + [(esc(nm), 1) for nm in names], mrows)
    first, last = L[0], L[-1]
    def sh(nm, i):
        tot = sum((P["paths"][x]["buyers"][i] or 0) for x in names)
        return sdiv(P["paths"][nm]["buyers"][i], tot)
    multi = [nm for nm in names if "+" in nm]
    def shift():
        if len(L) < 4:
            return ""
        a, b = len(L) - 3, len(L) - 1
        mv = sorted(((sh(nm, b) or 0) - (sh(nm, a) or 0), nm) for nm in names)
        dn, up = mv[0], mv[-1]
        return (f"Biggest shift {esc(L[a])} → {esc(L[b])}: {esc(up[1])} {pct(sh(up[1], a))} → {pct(sh(up[1], b))}; "
                f"{esc(dn[1])} {pct(sh(dn[1], a))} → {pct(sh(dn[1], b))}.")
    msh = lambda i: sum(sh(nm, i) or 0 for nm in multi)
    rd = reads([f"Buyers who saw more than one ad type: {pct(msh(0))} in {esc(first)} → {pct(msh(len(L)-1))} in {esc(last)}.",
                f"Largest path: {esc(names[0])}, {pct(sh(names[0], len(L)-1))} of ad-touched buyers in {esc(last)}.",
                f"Ad-touched buyers average {P['avg_touch_days']:.1f} touch days and {P['avg_days']:.1f} days from first touch to order.",
                shift()])
    return section("path", "Path to Conversion",
                   "For every buyer-month: the Sponsored Ads types the shopper saw or clicked in the 30 days before their first order "
                   "of that month. Shows the combination of ad types, not their order. Impressions count as touches.",
                   rd + "<h3>Share of ad-touched buyers by path</h3>" + ch1 + "<h3>Ad-touched buyers by path</h3>" + ch2
                   + "<h3>Path summary</h3>" + tb + "<h3>Monthly share by path</h3>" + tm)


def tab_ttc(f):
    T = f["ttc"]; order = ["Within 1 hour", "1-24 hours", "1-3 days", "4-7 days", "8-14 days"]
    blocks, rows = [], []
    for ad in ("sponsored_products", "sponsored_brands", "sponsored_display"):
        r_ = [t for t in T if t["ad"] == ad]
        if not r_:
            continue
        tot = sum(t["purchases"] for t in r_) or 1
        blocks.append(f"<div><h3>{AD[ad]}</h3>" + hbars([(t["bucket"], t["purchases"] / tot) for t in sorted(r_, key=lambda t: order.index(t["bucket"]))],
                                                       color={"sponsored_products": C_SP, "sponsored_brands": C_SB}.get(ad, C_SD)) + "<!--chart-end--></div>")
        cum = 0
        for t in sorted(r_, key=lambda t: order.index(t["bucket"])):
            cum += t["purchases"] / tot
            rows.append([AD[ad], t["bucket"], num(t["purchases"]), pct(t["purchases"] / tot), pct(cum), pct(sdiv(t["ntb"], t["purchases"])), money(t["sales"])])
    tb = table([("Ad type", 0), ("Click to purchase", 0), ("Purchases", 1), ("Share", 1), ("Cumulative", 1), ("NTB %", 1), ("Sales", 1)], rows)
    def share(ad, b):
        r_ = [t for t in T if t["ad"] == ad]; tot = sum(t["purchases"] for t in r_)
        x = [t for t in r_ if t["bucket"] == b]
        return sdiv(x[0]["purchases"], tot) if x else None
    def ntb(ad, b):
        x = [t for t in T if t["ad"] == ad and t["bucket"] == b]
        return sdiv(x[0]["ntb"], x[0]["purchases"]) if x else None
    rd = reads([f"Within 1 hour of the click: {pct(share('sponsored_products', 'Within 1 hour'))} of SP and {pct(share('sponsored_brands', 'Within 1 hour'))} of SB purchases.",
                f"SP purchases 8–14 days after the click: {pct(share('sponsored_products', '8-14 days'))} of SP purchases, {pct(ntb('sponsored_products', '8-14 days'))} of them NTB "
                f"(vs {pct(ntb('sponsored_products', 'Within 1 hour'))} within 1 hour)."])
    return section("ttc", "Time to Conversion", f"Time from ad click to purchase for click-attributed purchases, {esc(f['ttc_window'])}. "
                   "Purchases attribute for 14 days after the click.",
                   rd + '<div class="amc-grid2">' + "".join(blocks) + "</div><h3>Detail</h3>" + tb)


# ------------------------------------------------------------------ pages ---
# One standalone page per analysis. No overview page; each page carries its own KPIs and data notes.
def kpis_ntb(f):
    L, N = f["months"], f["ntb"]; i0, i1 = 0, len(L) - 1
    cpa = [sdiv(s, n) for s, n in zip(N["spend"], N["ntb_purchases"])]
    tot, pur = sum(N["ntb_purchases"]), sum(N["purchases"])
    return (kpi("NTB orders", num(tot), f"{L[i0]}–{L[i1]}")
            + kpi("NTB share of ad orders", pct(sdiv(N["ntb_purchases"][i1], N["purchases"][i1])),
                  f"{L[i1]} · {pct(sdiv(N['ntb_purchases'][i0], N['purchases'][i0]))} in {L[i0]}")
            + kpi("Spend per NTB order", money(cpa[i1]), f"{L[i1]} · {money(cpa[i0])} in {L[i0]}")
            + kpi("NTB share of window", pct(sdiv(tot, pur)), "NTB orders / ad-attributed orders"))


def kpis_repeat(f):
    L, Rp = f["months"], f["repeat"]; i0, i1 = 0, len(L) - 1
    has_sns = sum(v or 0 for v in Rp["sns_sales"]) > 0
    sh = lambda k, i: sdiv(Rp[k][i], Rp["sales"][i])
    out = ""
    if has_sns:
        out += kpi("SnS share of sales", pct(sh("sns_sales", i1)), f"{L[i1]} · {pct(sh('sns_sales', i0))} in {L[i0]}")
        out += kpi("SnS sign-ups", num(sum(v or 0 for v in Rp["signups"])), f"{L[i0]}–{L[i1]}")
    out += kpi("Repeat share of sales", pct(sh("repeat_sales", i1)), f"{L[i1]} · {pct(sh('repeat_sales', i0))} in {L[i0]}")
    out += kpi("One-time share of sales", pct(sh("one_sales", i1)), f"{L[i1]} · {pct(sh('one_sales', i0))} in {L[i0]}")
    return out


def kpis_path(f):
    L, P = f["months"], f["path"]; names = P["order"]; i1 = len(L) - 1
    tot = lambda i: sum((P["paths"][n]["buyers"][i] or 0) for n in names) or 1
    multi = sum((P["paths"][n]["buyers"][i1] or 0) for n in names if "+" in n) / tot(i1)
    return (kpi("Ad-touched buyers", num(P["total_touched"]), f"{L[0]}–{L[-1]}")
            + kpi("Saw 2+ ad types", pct(multi), L[i1])
            + kpi("Avg touch days", f"{P['avg_touch_days']:.1f}", "before first order of the month")
            + kpi("Avg days to order", f"{P['avg_days']:.1f}", "first touch → order"))


def kpis_ttc(f):
    T = f["ttc"]
    def s(ad, bs):
        r = [t for t in T if t["ad"] == ad]; tot = sum(t["purchases"] for t in r)
        return sdiv(sum(t["purchases"] for t in r if t["bucket"] in bs), tot)
    tot = sum(t["purchases"] for t in T)
    return (kpi("Click-attributed purchases", num(tot), f["ttc_window"])
            + kpi("SP within 1 hour", pct(s("sponsored_products", ["Within 1 hour"])), "of SP purchases")
            + kpi("SB within 1 hour", pct(s("sponsored_brands", ["Within 1 hour"])), "of SB purchases")
            + kpi("SP after 3 days", pct(s("sponsored_products", ["4-7 days", "8-14 days"])), "of SP purchases"))


PAGES = [
    # key, file, label (Home card / Pages switcher), sections, kpi fn, note
    ("new-to-brand", "new-to-brand.html", "New-to-Brand", [tab_ntb, tab_terms], kpis_ntb,
     "NTB customers and orders by month and ad type, and the search terms that bring them"),
    ("repeat-purchase", "repeat-purchase.html", "Repeat Purchase", [tab_repeat], kpis_repeat,
     "Subscribe & Save, repeat and one-time buyers by month and by ASIN"),
    ("path-to-conversion", "path-to-conversion.html", "Path to Conversion", [tab_path], kpis_path,
     "Ad types buyers saw in the 30 days before purchase, month by month"),
    ("time-to-conversion", "time-to-conversion.html", "Time to Conversion", [tab_ttc], kpis_ttc,
     "Time from ad click to purchase by ad type"),
]
OLD_FILES = ["amc.html", "amc-ntb.html", "amc-repeat.html", "amc-path.html", "amc-ttc.html"]
SEC_LABEL = dict(NAV)


def page_doc(f, lb, title, sections, kfn):
    m = f["meta"]; L = f["months"]
    notes = "".join(f"<li>{n}</li>" for n in f.get("notes", []))
    head = (f'<p class="amc-intro">Amazon Marketing Cloud · {esc(m["brand"])} · complete months {esc(L[0])} – {esc(L[-1])}. '
            "Data only; every number comes from the AMC queries listed in the footer.</p>"
            f'<div class="amc-kpis">{kfn(f)}</div>')
    body = head + "".join(t(f) for t in sections) + (
        f'<h3>Data notes</h3><ul class="amc-note" style="margin-left:18px">{notes}</ul>' if notes else "")
    secs = [t.__name__.replace("tab_", "") for t in sections]
    keymap = {"overview": "overview", "ntb": "ntb", "terms": "ntb_terms", "repeat": "repeat", "path": "path", "ttc": "ttc"}
    nav = "".join(f'<li><a href="#{keymap[k]}">{SEC_LABEL[keymap[k]]}</a></li>' for k in secs) if len(secs) > 1 else ""
    dates = "".join(f"<div><b>{esc(k)}:</b> {esc(v)}</div>" for k, v in m["windows"])
    links = {"items": [{"key": "drive_folder", "label": "Drive folder", "group": "client", "url": None},
                       {"key": "slack_channel", "label": "Slack channel", "group": "client", "url": None},
                       {"key": "seller_central", "label": "Seller Central", "group": "client", "url": "https://sellercentral.amazon.com"},
                       {"key": "ads_console", "label": "Ads console", "group": "client", "url": "https://advertising.amazon.com"}],
             "client_files": [], "pages": []}
    extra = f'<nav class="tabs"><ul>{nav}</ul></nav>' if nav else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(m['brand'])} — {esc(title)}</title>
<style>{R.BASE_CSS}{R.EXTRA_CSS}{CSS}.amc-intro{{font-size:13px;color:{B.MUTED};margin:0 0 14px}}{H.HEADER_CSS}</style></head><body>
{H.head_block(links, m["brand"], lb, m['marketplace'], m['pulled'], extra_bar=extra, period=m['period'])}
<main>{body}</main>
<footer><div class="foot-dates">{dates}</div><div class="disclaimer">{B.DISCLAIMER}</div>
<div style="margin-top:10px;opacity:0.6;">{B.BRAND_NAME} &middot; {esc(m['brand'])} &middot; {esc(title)} &middot; {m['pulled']}</div></footer>
{H.scripts_block(links)}
</body></html>"""


def build(findings, out_dir, logo=B.LOGO_HERO):
    """Writes one HTML per analysis into out_dir and pages.json (key, file, label, note) for publishing."""
    f = json.load(open(findings)); lb = R.load_logo_b64(logo)
    os.makedirs(out_dir, exist_ok=True)
    manifest = []
    for old in OLD_FILES:
        if os.path.exists(os.path.join(out_dir, old)):
            os.remove(os.path.join(out_dir, old))
    for key, fn, label, sections, kfn, blurb in PAGES:
        open(os.path.join(out_dir, fn), "w").write(page_doc(f, lb, label, sections, kfn))
        manifest.append({"key": key, "file": fn, "label": label, "note": f"{f['meta']['period']} · {blurb}"})
    json.dump(manifest, open(os.path.join(out_dir, "pages.json"), "w"), indent=1)
    return [m["file"] for m in manifest]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True); ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    print("[done]", build(a.findings, a.out_dir))
