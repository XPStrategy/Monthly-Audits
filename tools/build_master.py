#!/usr/bin/env python3
"""Build the master hub (hub/index.html): one page listing every account hub with its links.

Reads accounts/*/links.json, so it always matches what is published. publish_monthly.py calls
build(repo) after every init / review / page publish; it can also be run on its own:
    python3 tools/build_master.py --repo .
"""
import argparse, glob, json, os, re, sys

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


TEAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "account_team.json")


def team():
    return json.load(open(TEAM_FILE)) if os.path.exists(TEAM_FILE) else {}


def rows(repo):
    T = team()
    out = []
    for lj in sorted(glob.glob(os.path.join(repo, "accounts", "*", "links.json"))):
        m = json.load(open(lj)); slug = m["slug"]
        pages = m.get("all_pages", m.get("pages", []))
        reviews = [p for p in pages if p.get("kind") != "page"]
        amc = [p for p in pages if p.get("key") in AMC_KEYS]
        url = {i["key"]: i.get("url") for i in m.get("items", [])}
        out.append({"brand": m["brand"], "slug": slug, 
                    "latest": reviews[0] if reviews else None, "n_reviews": len(reviews),
                    "amc_live": sum(1 for p in amc if p.get("status") != "placeholder"), "amc_total": len(amc),
                    "amc_first": next((p["file"] for p in amc), None),
                    "drive": url.get("drive_folder"),
                    **(lambda t: {"am": t.get("am", ""), "ppc": t.get("ppc", []), "status": t.get("status", "active"),
                                  "note": t.get("note", "")})(T.get(m.get("client") or re.sub(r"-[0-9a-f]{8}$", "", slug), {}))})
    return sorted(out, key=lambda r: r["brand"].lower())


STATUS = {"active": "Active", "offboarding": "Offboarding", "inactive": "Inactive"}


def page(rs, today):
    base = "../accounts/"
    ams = sorted({r["am"] for r in rs if r["am"]}); ppcs = sorted({p for r in rs for p in r["ppc"]})
    opts = "".join(f'<option value="{esc(r["slug"])}">{esc(r["brand"])}</option>' for r in rs if r["status"] != "inactive")
    sel = lambda id_, lab, vals: (f'<select id="{id_}" aria-label="{lab}"><option value="">{lab}: all</option>'
                                  + "".join(f'<option value="{esc(v)}">{lab}: {esc(v)}</option>' for v in vals) + "</select>")
    trs = []
    for r in rs:
        h = f'{base}{r["slug"]}/'
        lat = (f'<a href="{h}{esc(r["latest"]["file"])}">{esc(r["latest"]["label"])}</a>'
               + (f' <span class="na">+{r["n_reviews"] - 1} older</span>' if r["n_reviews"] > 1 else "")) if r["latest"] else '<span class="na">None yet</span>'
        amc = (f'<a href="{h}{esc(r["amc_first"])}"><span class="pill on">{r["amc_live"]} of {r["amc_total"]} live</span></a>'
               if r["amc_live"] else f'<span class="pill">Not published</span>')
        lk = lambda u, t: f'<a href="{esc(u)}" target="_blank" rel="noopener">{t}</a>' if u else '<span class="na">—</span>'
        st = "" if r["status"] == "active" else f' <span class="pill st-{r["status"]}">{STATUS[r["status"]]}</span>'
        note = f'<div class="na" style="font-size:12px">{esc(r["note"])}</div>' if r["note"] else ""
        trs.append(f'<tr data-slug="{esc(r["slug"])}" data-q="{esc((r["brand"] + " " + r["note"]).lower())}" data-am="{esc(r["am"])}"'
                   f' data-ppc="|{esc("|".join(r["ppc"]))}|" data-st="{r["status"]}">'
                   f'<td data-l="Account"><a class="hubl" href="{h}">{esc(r["brand"])}</a>{st}{note}</td>'
                   f'<td data-l="AM">{esc(r["am"]) or "<span class=na>—</span>"}</td>'
                   f'<td data-l="PPC">{esc(", ".join(r["ppc"])) or "<span class=na>—</span>"}</td>'
                   f'<td data-l="Latest review">{lat}</td><td data-l="AMC Reviews">{amc}</td>'
                   f'<td data-l="Drive">{lk(r["drive"], "Folder")}</td></tr>')
    meta = {"items": [], "client_files": [], "pages": []}
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>XP Strategy Analysis - Account Hubs</title>
<style>{P.HUB_CSS}{H.HEADER_CSS}{CSS}
.pill.st-offboarding {{ border-color: {B.ACCENT}; color: {B.DARK}; }}
.pill.st-inactive {{ background: #f1f2f4; }}
tr.inactive td {{ opacity: .6; }}
.xph-meta > div:last-child {{ display: none; }}
</style></head><body>
{H.hero_html("Account Hubs", P.logo_b64(), "US", today, None)}
<main><h2>Account Hubs</h2>
<div class="tools">
  <select id="pick" aria-label="Open an account hub"><option value="">Open an account hub…</option>{opts}</select>
  {sel("am", "AM", ams)}{sel("ppc", "PPC", ppcs)}
  <select id="st" aria-label="Status"><option value="current">Current accounts</option><option value="inactive">Inactive</option><option value="">All accounts</option></select>
  <input id="q" type="search" placeholder="Filter accounts" aria-label="Filter accounts">
  <span class="count" id="count"></span>
</div>
<div class="wrap"><table><thead><tr><th>Account</th><th>AM</th><th>PPC</th><th>Latest review</th><th>AMC Reviews</th><th>Drive</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<p class="source" style="font-size:12px;color:{B.MUTED};margin-top:8px">Source: each account's links.json in the Monthly-Audits repo, rebuilt on every publish; AM and PPC from tools/account_team.json (Account Distribution sheet).</p>
</main>
{H.footer_html(B.DISCLAIMER, 'all account hubs', 'Account Hubs', today)}
<script>
(function(){{
  var $ = function(i){{ return document.getElementById(i); }}, rows = [].slice.call(document.querySelectorAll('tbody tr'));
  rows.forEach(function(r){{ if (r.getAttribute('data-st') === 'inactive') r.className = 'inactive'; }});
  $('pick').addEventListener('change', function(){{ if ($('pick').value) location.href = '{base}' + $('pick').value + '/'; }});
  function apply(){{
    var t = $('q').value.trim().toLowerCase(), am = $('am').value, ppc = $('ppc').value, st = $('st').value, n = 0;
    rows.forEach(function(r){{
      var s = r.getAttribute('data-st');
      var ok = (!t || r.getAttribute('data-q').indexOf(t) >= 0) && (!am || r.getAttribute('data-am') === am)
        && (!ppc || r.getAttribute('data-ppc').indexOf('|' + ppc + '|') >= 0)
        && (st === '' || (st === 'current' ? s !== 'inactive' : s === st));
      r.style.display = ok ? '' : 'none'; if (ok) n++;
    }});
    $('count').textContent = n + ' account' + (n === 1 ? '' : 's');
    try {{ localStorage.setItem('xp-hub-f', JSON.stringify({{am: am, ppc: ppc, st: st}})); }} catch (e) {{}}
  }}
  try {{ var f = JSON.parse(localStorage.getItem('xp-hub-f') || '{{}}'); ['am','ppc','st'].forEach(function(k){{ if (f[k] !== undefined) $(k).value = f[k]; }}); }} catch (e) {{}}
  ['am','ppc','st'].forEach(function(k){{ $(k).addEventListener('change', apply); }}); $('q').addEventListener('input', apply);
  apply();
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
