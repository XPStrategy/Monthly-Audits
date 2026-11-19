#!/usr/bin/env python3
"""Render the bulk-upload blocks of the Monthly Account Review.

    from bulk_render import render_blocks           # used by build_account_review.py
    python3 bulk_render.py <account_dir> --inject <review.html> --out <new.html>   # add to an existing page

Each block sits at the end of its tab (budgets, wasted, harvest, products) and carries the .xlsx inline as a
download link, so the page stays one self-contained file.
"""
import argparse, base64, datetime as dt, html, json, os, re

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSS = """
.bulk { border-left:3px solid #111318; }
.bulk-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }
.bulk-head h3 { margin:0 0 4px; }
.bulk-tag { font-size:10.5px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; color:#666666; }
a.dl-btn { display:inline-flex; align-items:center; gap:8px; background:#111318; color:#fff; text-decoration:none;
           font-size:13px; font-weight:600; padding:9px 14px; border-radius:5px; white-space:nowrap; }
a.dl-btn:hover { background:#2b2f38; }
a.dl-btn svg { width:15px; height:15px; }
.bulk-meta { display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12.5px; color:#1a1d24; margin:10px 0 12px; }
.bulk-meta b { font-weight:700; }
.bulk-rule { font-size:12px; color:#666666; margin:0 0 12px; }
.bulk details { margin-top:10px; }
.bulk-none { font-size:13px; color:#666666; }
h2.has-dl { display:flex; justify-content:space-between; align-items:center; gap:10px 16px; flex-wrap:wrap; }
h2.has-dl .h2-dl { display:flex; gap:8px; flex-wrap:wrap; }
h2 a.dl-btn { font-size:13px; letter-spacing:0; line-height:1.2; }
details.bulk > summary { cursor:pointer; list-style:none; display:flex; flex-direction:column; gap:3px; }
details.bulk > summary::-webkit-details-marker { display:none; }
details.bulk > summary .bulk-title { font-size:15px; font-weight:600; color:#111318; }
details.bulk > summary .bulk-title::after { content:"  Show rows ▾"; font-size:12px; font-weight:500; color:#666666; }
details.bulk[open] > summary .bulk-title::after { content:"  Hide ▴"; }
details.bulk[open] > summary { margin-bottom:6px; }
"""
ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 21h16"/></svg>'


def esc(s):
    return html.escape("" if s is None else str(s))


def money(v, d=0):
    return "—" if v is None else f"${v:,.{d}f}"


def pct(v, d=0):
    return "—" if v is None else f"{v*100:.{d}f}%"


def num(v):
    return "—" if v is None else f"{v:,.0f}"


def table(head, rows):
    th = "".join(f'<th class="{"num" if a else ""}">{h}</th>' for h, a in head)
    trs = "".join("<tr>" + "".join(f'<td class="{"num" if head[i][1] else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="table-scroll"><table class="data compact"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


LINK_BASE = None   # set to a relative folder (e.g. "bulk/2026-11") to link the files instead of embedding them


def dl(acct, fname, label):
    if not fname:
        return ""
    if LINK_BASE:
        href = f"{LINK_BASE}/{fname}"
    else:
        href = f"data:{XLSX};base64," + base64.b64encode(open(os.path.join(acct, "bulk", fname), "rb").read()).decode()
    return f'<a class="dl-btn" download="{esc(fname)}" href="{esc(href)}">{ICON}{esc(label)}</a>'


def card(tag, title, btn, meta, rule, body, extra="", src=""):
    m = "".join(f"<span>{x}</span>" for x in meta)
    btn_html = f'<!--btn-->{btn}<!--/btn-->' if btn else ""
    return f"""{btn_html}<details class="card bulk"><summary><span class="bulk-tag">{tag}</span><span class="bulk-title">{title}</span></summary>
  <div class="bulk-meta">{m}</div><p class="bulk-rule">{esc(rule)}</p>{body}{extra}<p class="src">Source: {esc(src)}</p></details>"""


def render_blocks(bulk, acct, lag=None):
    f = bulk["files"]; T = bulk.get("reference_acos"); built = dt.date.fromisoformat(bulk["run_date"]).strftime("%b %-d, %Y")
    tag = f"Bulk upload file · built {built}"
    live_note = (f'<p class="sub">Checked against the live account ({esc(bulk.get("live_state"))}): rows that already exist, and ad groups that are not enabled, are left out.</p>'
                 if "bulk download" in str(bulk.get("live_state", "")) or "API" in str(bulk.get("live_state", "")) else
                 '<p class="sub">No live campaign list for this run: existing keywords and negatives were checked against report data only.</p>')
    foot = live_note + ('<p class="sub">Amazon Ads bulksheet (Sponsored Products). IDs are stored as text; the metric columns are for review '
            'only and are ignored by Amazon on upload. Review before uploading in Amazon Ads &rarr; Bulk operations.</p>')
    out = {}

    # ---- budgets
    b = bulk["budgets"]
    rows = [[esc(x["campaign"]), money(x["budget"]), money(x["suggested"]), pct(x["tib"]), pct(x["acos_l30"]),
             f'{money(x["missed_sales"][0])}–{money(x["missed_sales"][1])}'] for x in b["included"]]
    body = table([("Campaign", 0), ("Daily Budget", 1), ("New Budget", 1), ("Time in Budget", 1), ("ACoS 30d", 1), ("Est. Missed Sales 7d", 1)], rows) if rows \
        else '<p class="bulk-none">No budget-constrained campaign is at or below the reference ACoS.</p>'
    exc = ""
    if b["excluded"]:
        er = [[esc(x["campaign"]), money(x["budget"]), money(x["suggested"]), pct(x["tib"]), pct(x["acos_l30"]), esc(x["reason"])] for x in b["excluded"]]
        exc = f'<details><summary>{len(er)} constrained campaigns not in the file</summary>{table([("Campaign", 0), ("Daily Budget", 1), ("Amazon Suggested", 1), ("Time in Budget", 1), ("ACoS 30d", 1), ("Reason", 0)], er)}</details>'
    out["budgets"] = card(tag, "Budget updates", dl(acct, f.get("budgets"), "Budget file"),
                          [f"<b>{len(b['included'])}</b> campaign{'' if len(b['included']) == 1 else 's'} updated", f"Reference ACoS <b>{pct(T, 1)}</b>", f"Budget check {esc(b.get('window'))}"],
                          b["rule"], body, exc + foot, "Amazon Ads budget recommendations and campaign reports")

    # ---- negatives
    n = bulk["negatives"]
    rows = [[esc(x["term"].upper() if re.match(r"^b0[a-z0-9]{8}$", x["term"]) else x["term"]), esc(x["class"]), money(x["spend"]), num(x["clicks"]),
             num(x["ad_groups"]), esc(x.get("note", ""))] for x in n["included"]]
    body = table([("Search Term", 0), ("Type", 0), ("Spend", 1), ("Clicks", 1), ("Ad Groups Negated", 1), ("Note", 0)], rows)
    exc = ""
    if n["excluded"]:
        er = [[esc(x["term"]), esc(x["class"]), money(x["spend"]), num(x["clicks"]), esc(x["reason"])] for x in n["excluded"]]
        exc = f'<details><summary>{len(er)} zero-order terms over the threshold left out of the file</summary>{table([("Search Term", 0), ("Type", 0), ("Spend", 1), ("Clicks", 1), ("Reason", 0)], er)}</details>'
    out["wasted"] = card(tag, "Negative keywords from wasted spend", dl(acct, f.get("negatives"), "Negatives file"),
                         [f"<b>{len(n['included'])}</b> search terms", f"<b>{n['rows']}</b> negative rows", f"<b>{money(n['spend'])}</b> zero-order spend",
                          f"Window {esc(lag) if lag else 'conversion-complete'}"], n["rule"], body, exc + foot, "Amazon Ads search term reports, conversion-complete window")

    # ---- harvest
    h = bulk["harvest"]; parts = []
    rows = [[esc(x["term"].upper() if re.match(r"^b0[a-z0-9]{8}$", x["term"]) else x["term"]), esc(x["class"]), esc(x["asin"]), num(x["orders"]), money(x["sales"]),
             pct(x["acos"]), money(x["bid"], 2)] for x in h["included"]]
    exc = ""
    if h["excluded"]:
        er = [[esc(x["term"]), num(x["orders"]), money(x["sales"]), pct(x["acos"]), esc(x["reason"])] for x in h["excluded"]]
        exc = f'<details><summary>{len(er)} converting terms left out of the file</summary>{table([("Search Term", 0), ("Orders", 1), ("Sales", 1), ("ACoS", 1), ("Reason", 0)], er)}</details>'
    parts.append(card(tag, "Harvest: converting search terms to Exact", dl(acct, f.get("harvest_search_terms"), "Harvest: search terms"),
                      [f"<b>{len(h['included'])}</b> keywords", f"<b>{h.get('ad_groups', 0)}</b> ad groups",
                       f"New campaign <b>{esc(h.get('campaign'))}</b>", f"Daily budget <b>{money(h.get('daily_budget'))}</b>"],
                      h["rule"], table([("Search Term", 0), ("Type", 0), ("ASIN", 0), ("Orders", 1), ("Sales", 1), ("ACoS", 1), ("Bid", 1)], rows), exc + foot, "Amazon Ads search term and advertised product reports; Brand Analytics Search Query Performance"))
    q = bulk["sqp_harvest"]
    rows = [[esc(x["term"]), esc(x["class"]), esc(x["asin"]), num(x["brand_purchases"]), num(x["brand_clicks"]), money(x["paid_spend"]),
             money(x["bid"], 2), esc(x["bid_source"])] for x in q["included"]]
    parts.append(card(tag, "Harvest: Search Query Performance queries to Exact", dl(acct, f.get("harvest_sqp"), "Harvest: SQP"),
                      [f"<b>{len(q['included'])}</b> keywords", f"<b>{q.get('ad_groups', 0)}</b> ad groups", f"New campaign <b>{esc(q.get('campaign'))}</b>",
                       f"Daily budget <b>{money(q.get('daily_budget'))}</b>", f"Brand Analytics 8 weeks to {esc(q.get('window_end'))}"],
                      q["rule"], table([("Search Query", 0), ("Type", 0), ("ASIN", 0), ("Brand Purchases", 1), ("Brand Clicks", 1), ("Paid Spend", 1), ("Bid", 1), ("Bid Basis", 0)], rows), foot, "Brand Analytics Search Query Performance; Amazon Ads search term reports"))
    out["harvest"] = "\n".join(parts)

    # ---- products
    p = bulk["products"]
    rows = [[f'{esc(x["name"] or "")}<div class="sub">{esc(x["asin"])}</div>', esc(x["status"]) + ("" if x.get("live_ad") is None else ('<div class="sub">enabled ad exists</div>' if x["live_ad"] else '<div class="sub">no enabled ad</div>')), money(x["sales_60"]), num(x["units_60"]), money(x["ad_spend_60"]),
             f'{x["ratio"]:.2f}x', num(x["available"]), "—" if x["weeks_cover"] is None else f'{x["weeks_cover"]:.1f}',
             ("In file" if x.get("file") else esc(x.get("reason", ""))) if "file" in x else ("under $1,000 sales" if x["sales_60"] < 1000 else "listed only")]
            for x in sorted(p["rows"], key=lambda x: (x["ratio"], -x["sales_60"]))]
    body = table([("Product", 0), ("Status", 0), ("Total Sales 60d", 1), ("Units 60d", 1), ("Ad Spend 60d", 1), ("Spend Share ÷ Sales Share", 1),
                  ("FBA Avail.", 1), ("Weeks of Cover", 1), ("Bulk File", 0)], rows)
    out["products"] = card(tag, "Products selling with little or no ad spend", dl(acct, f.get("product_push"), "Product push file"),
                           [f"<b>{sum(1 for x in p['push'] if x.get('file'))}</b> ASINs in file", f"New campaign <b>{esc(p.get('campaign'))}</b>",
                            f"Daily budget <b>{money(p.get('daily_budget'))}</b>", f"Default bid <b>{money(p['auto_bid'], 2)}</b>"],
                           p["rule"] + " Under-invested = spend share below 0.7x sales share (listed, not in the file).", body, foot, "Seller Central Business Reports and FBA inventory planning report; Amazon Ads advertised product reports")
    # ---- overview: one list of every file, with a link to the tab that explains it
    S = lambda x: f'<a href="#{x}">{ {"wasted": "Wasted Spend", "harvest": "Harvest", "products": "Products", "budgets": "Budgets & Q4"}[x]} &rarr;</a>'
    items = [("negatives", "Negative keywords", f"{len(n['included'])} terms · {n['rows']} rows · {money(n['spend'])} zero-order spend", "wasted"),
             ("harvest_search_terms", "Harvest: search terms to Exact", f"{len(h['included'])} keywords · new campaign {money(h.get('daily_budget'))}/day", "harvest"),
             ("harvest_sqp", "Harvest: SQP queries to Exact", f"{len(q['included'])} keywords · new campaign {money(q.get('daily_budget'))}/day", "harvest"),
             ("product_push", "Product push (Auto)", f"{sum(1 for x in p['push'] if x.get('file'))} ASINs · new campaign {money(p.get('daily_budget'))}/day", "products"),
             ("budgets", "Budget updates", f"{len(b['included'])} campaign{'' if len(b['included']) == 1 else 's'} · {len(b['excluded'])} constrained campaign{'' if len(b['excluded']) == 1 else 's'} left out", "budgets")]
    rows = [[esc(lbl), esc(det), dl(acct, f.get(k), "Download") if f.get(k) else "No rows this month", S(tab)] for k, lbl, det, tab in items]
    out["overview"] = f"""<div class="card bulk"><div class="bulk-head"><div><div class="bulk-tag">{tag}</div><h3>Bulk Upload Files</h3></div></div>
  <p class="bulk-rule">Amazon Ads bulksheets built from this review's data. Each tab explains the rule and lists what was left out. Review before uploading in Amazon Ads &rarr; Bulk operations.</p>
  {table([("File", 0), ("Contents", 0), ("Download", 0), ("Details", 0)], rows)}<p class="src">Source: Amazon Ads search term, campaign and advertised product reports; Amazon Ads budget recommendations; Brand Analytics Search Query Performance; Seller Central Business Reports</p></div>"""
    return out


def inject(page, blocks):
    return inject_html(open(page).read(), blocks)


def inject_html(s, blocks):
    s = re.sub(r"/\*bulk-css\*/.*?/\*/bulk-css\*/", "", s, flags=re.S)
    s = s.replace("</style>", "/*bulk-css*/" + CSS + "/*/bulk-css*/</style>", 1)
    s = re.sub(r'<!--bulk:[a-z0-9]+-->.*?<!--/bulk-->', "", s, flags=re.S)        # re-runnable
    s = s.replace('<h2 class="has-dl">', "<h2>")
    for sec, h in blocks.items():
        if sec == "overview":
            m = re.search(r'<h3>Alerts This Month</h3>.*?</ul>.*?</div>', s, re.S)
            if m:
                s = s[:m.end()] + f"\n  <!--bulk:{sec}-->{h}<!--/bulk-->" + s[m.end():]
                continue
        btns = re.findall(r"<!--btn-->(.*?)<!--/btn-->", h, re.S)
        h = re.sub(r"<!--btn-->.*?<!--/btn-->", "", h, flags=re.S)
        if btns:
            s = re.sub(rf'(<section id="{sec}">\s*)<h2>(.*?)</h2>',
                       lambda mm: f'{mm.group(1)}<h2 class="has-dl">{mm.group(2)}<!--bulk:h2--><span class="h2-dl">{"".join(btns)}</span><!--/bulk--></h2>',
                       s, count=1, flags=re.S)
        m = re.search(rf'<section id="{sec}">.*?(</section>)', s, re.S)
        if not m:
            raise SystemExit(f"section {sec} not found")
        s = s[:m.start(1)] + f"<!--bulk:{sec}-->{h}<!--/bulk-->\n" + s[m.start(1):]
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("acct"); ap.add_argument("--inject", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--lag", default=None); ap.add_argument("--link-base", default=None)
    a = ap.parse_args(); LINK_BASE = a.link_base
    bulk = json.load(open(os.path.join(a.acct, "bulk.json")))
    html_out = inject(a.inject, render_blocks(bulk, a.acct, a.lag))   # read fully before writing (in-place safe)
    open(a.out, "w").write(html_out)
    print("written", a.out, os.path.getsize(a.out))
