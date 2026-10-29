#!/usr/bin/env python3
"""Build the master hub (hub/index.html): one page listing every account hub with its links.

Reads accounts/*/links.json, so it always matches what is published. publish_monthly.py calls
build(repo) after every init / review / page publish; it can also be run on its own:
    python3 tools/build_master.py --repo .
"""
import argparse, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_monthly as P  # noqa: E402

B, H, esc = P.B, P.H, P.esc

CSS = """
.tools { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin: 0 0 18px; }
.tools select, .tools input { font: inherit; font-size: 14px; padding: 8px 10px; border: 1px solid %(border)s;
  border-radius: 6px; background: #fff; color: %(ink)s; min-width: 0; }
.tools input { flex: 1 1 220px; }
.tools select { flex: 0 1 300px; }
.count { font-size: 12.5px; color: %(muted)s; }
table { width: 100%%; border-collapse: collapse; background: #fff; border: 1px solid %(border)s; border-radius: 6px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid %(border)s; font-size: 13.5px; vertical-align: top; }
th { background: %(dark)s; color: #fff; font-weight: 600; font-size: 12px; letter-spacing: .3px; text-transform: uppercase; }
tr.hit td { background: #fff7e8; }
td a { color: %(dark)s; }
a.hubl { font-weight: 600; text-decoration: none; border-bottom: 2px solid %(accent)s; }
.pill { display:inline-block; font-size: 11.5px; padding: 2px 8px; border-radius: 10px; border: 1px solid %(border)s; color: %(muted)s; white-space: nowrap; }
.pill.on { border-color: %(accent)s; color: %(dark)s; }
.na { color: %(muted)s; }
.wrap { overflow-x: auto; }
@media (max-width: 720px) {
  table, thead, tbody, tr, td { display: block; width: 100%%; }
  thead { display: none; }
  tr { border-bottom: 1px solid %(border)s; padding: 8px 0; }
  td { border: 0; padding: 4px 12px; }
  td[data-l]::before { content: attr(data-l) ": "; color: %(muted)s; font-size: 12px; }
}
""" % dict(border=B.BORDER, ink=B.INK, dark=B.DARK, muted=B.MUTED, accent=B.ACCENT)

AMC_KEYS = [k for k, s in P.SECTION_OF.items() if s == "amc"]


def rows(repo):
    out = []
    for lj in sorted(glob.glob(os.path.join(repo, "accounts", "*", "links.json"))):
        m = json.load(open(lj)); slug = m["slug"]
        pages = m.get("all_pages", m.get("pages", []))
        reviews = [p for p in pages if p.get("kind") != "page"]
        amc = [p for p in pages if p.get("key") in AMC_KEYS]
        url = {i["key"]: i.get("url") for i in m.get("items", [])}
        out.append({"brand": m["brand"], "slug": slug, "channel": m.get("slack_channel", ""),
                    "latest": reviews[0] if reviews else None, "n_reviews": len(reviews),
                    "amc_live": sum(1 for p in amc if p.get("status") != "placeholder"), "amc_total": len(amc),
                    "amc_first": next((p["file"] for p in amc), None),
                    "drive": url.get("drive_folder"), "slack": url.get("slack_channel")})
    return sorted(out, key=lambda r: r["brand"].lower())


def page(rs, today):
    base = "../accounts/"
    opts = "".join(f'<option value="{esc(r["slug"])}">{esc(r["brand"])}</option>' for r in rs)
    trs = []
    for r in rs:
        h = f'{base}{r["slug"]}/'
        lat = (f'<a href="{h}{esc(r["latest"]["file"])}">{esc(r["latest"]["label"])}</a>'
               + (f' <span class="na">+{r["n_reviews"] - 1} older</span>' if r["n_reviews"] > 1 else "")) if r["latest"] else '<span class="na">None yet</span>'
        amc = (f'<a href="{h}{esc(r["amc_first"])}"><span class="pill on">{r["amc_live"]} of {r["amc_total"]} live</span></a>'
               if r["amc_live"] else f'<span class="pill">Not published</span>')
        lk = lambda u, t: f'<a href="{esc(u)}" target="_blank" rel="noopener">{t}</a>' if u else '<span class="na">—</span>'
        trs.append(f'<tr data-slug="{esc(r["slug"])}" data-q="{esc((r["brand"] + " " + r["channel"]).lower())}">'
                   f'<td data-l="Account"><a class="hubl" href="{h}">{esc(r["brand"])}</a></td>'
                   f'<td data-l="Latest review">{lat}</td><td data-l="AMC Reviews">{amc}</td>'
                   f'<td data-l="Drive">{lk(r["drive"], "Folder")}</td></tr>')
    n_rev = sum(1 for r in rs if r["latest"]); n_amc = sum(1 for r in rs if r["amc_live"])
    meta = {"items": [], "client_files": [], "pages": []}
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>XP Strategy Analysis - Account Hubs</title>
<style>{P.HUB_CSS}{H.HEADER_CSS}{CSS}</style></head><body>
{H.hero_html("Account Hubs", P.logo_b64(), "US", today, None)}
<main><h2>Account Hubs</h2>
<div class="tools">
  <select id="pick" aria-label="Open an account hub"><option value="">Open an account hub…</option>{opts}</select>
  <input id="q" type="search" placeholder="Filter accounts" aria-label="Filter accounts">
  <span class="count" id="count">{len(rs)} accounts · {n_rev} with a monthly review · {n_amc} with AMC Reviews</span>
</div>
<div class="wrap"><table><thead><tr><th>Account</th><th>Latest review</th><th>AMC Reviews</th><th>Drive</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<p class="source" style="font-size:12px;color:{B.MUTED};margin-top:8px">Source: each account's links.json in the Monthly-Audits repo, rebuilt on every publish.</p>
</main>
{H.footer_html(B.DISCLAIMER, 'all account hubs', 'Account Hubs', today)}
<script>
(function(){{
  var pick = document.getElementById('pick'), q = document.getElementById('q'), rows = [].slice.call(document.querySelectorAll('tbody tr'));
  pick.addEventListener('change', function(){{ if (pick.value) location.href = '{base}' + pick.value + '/'; }});
  q.addEventListener('input', function(){{
    var t = q.value.trim().toLowerCase(), n = 0;
    rows.forEach(function(r){{ var ok = !t || r.getAttribute('data-q').indexOf(t) >= 0; r.style.display = ok ? '' : 'none'; if (ok) n++; }});
    document.getElementById('count').textContent = n + ' of {len(rs)} accounts';
  }});
}})();
</script>
</body></html>"""


def build(repo):
    from datetime import date
    rs = rows(repo)
    os.makedirs(os.path.join(repo, "hub"), exist_ok=True)
    p = os.path.join(repo, "hub", "index.html")
    open(p, "w").write(page(rs, date.today().isoformat()))
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default=".")
    print("[done]", build(ap.parse_args().repo))
