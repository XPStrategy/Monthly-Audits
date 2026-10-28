#!/usr/bin/env python3
"""
Publish one client's Monthly Account Review to the XP Strategy Monthly-Audits repo
(GitHub Pages). Internal pages: XP team only, never sent to clients.

Writes, inside a local clone of this repo:

    accounts/<client>-<8 hex>/index.html     Home: one card per month, newest first (the ONE link)
    accounts/<client>-<8 hex>/<yyyy-mm>.html  that month's review
    accounts/<client>-<8 hex>/links.json      months + links (Drive folder, Slack channel, consoles)

<client> is the Slack channel name without "xps-" (cosmo-technologies, displate ...).
The 8-hex suffix is derived from the client slug, so every month lands in the same folder
and the link never changes. Previous months are kept; re-publishing a month replaces it.

The four review scripts stay at the repo root: the xp-monthly-account-review skill
downloads them from there by name. Never move them.

Usage:
    python3 tools/publish_monthly.py --repo . --client cosmo-technologies \
        --brand "JrTrack by Cosmo" --month 2026-11 --review Cosmo_Monthly_Account_Review.html \
        [--drive-folder <folder id>] [--slack-channel-id <C...>] [--marketplace US] \
        [--commit] [--push]

Prints the Home URL and the month URL.
"""
import argparse
import glob
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone

PAGES_BASE = "https://xpstrategy.github.io/Monthly-Audits"
SLACK_TEAM = "https://app.slack.com/client"   # channel links open in the Slack web app

# Shared XP header (same hero, links bar and footer as the prospect audit pages).
_cands = [os.environ.get("XP_AUDIT_SCRIPTS", "")]
for _name in ("xp-audit-prospect", "amazon-ads-prospect-audit"):
    for _root in ("/mnt/skills", os.path.expanduser("~/.claude/skills"), "/root/.claude/skills"):
        _cands += glob.glob(os.path.join(_root, "**", _name, "scripts"), recursive=True)
AUDIT_SCRIPTS = next((c for c in _cands if c and os.path.exists(os.path.join(c, "xp_header.py"))), None)
if not AUDIT_SCRIPTS:
    sys.exit("xp-audit-prospect skill not found: install it in this session (the header lives there).")
sys.path.insert(0, AUDIT_SCRIPTS)
import brand as B        # noqa: E402
import xp_header as H    # noqa: E402


def esc(s):
    return html.escape(str(s or ""), quote=True)


def folder_slug(client):
    client = re.sub(r"^xps-", "", client.strip().lower())
    client = re.sub(r"[^a-z0-9-]+", "-", client).strip("-")
    return f"{client}-{hashlib.sha256(('xp-monthly:' + client).encode()).hexdigest()[:8]}"


def month_label(ym):
    y, m = map(int, ym.split("-"))
    return date(y, m, 1).strftime("%B %Y")


def logo_b64():
    import base64
    try:
        with open(B.LOGO_HERO, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return None


HUB_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; background: %(bg)s; color: %(ink)s; line-height: 1.55; }
main { max-width: 1180px; margin: 0 auto; padding: 30px 40px 40px; }
h2 { font-size: 22px; font-weight: 600; color: %(dark)s; margin-bottom: 18px;
     border-bottom: 2px solid %(border)s; padding-bottom: 10px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.card { display: block; background: #fff; border: 1px solid %(border)s; border-left: 4px solid %(border)s;
        border-radius: 6px; padding: 18px; text-decoration: none; color: %(ink)s; }
.card.latest { border-left-color: %(accent)s; }
.card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); }
.card b { display: block; font-size: 16px; margin-bottom: 6px; color: %(dark)s; }
.card span { font-size: 12.5px; color: %(muted)s; }
@media (max-width: 720px) { main { padding: 20px 16px 30px; } }
""" % dict(bg=B.BG, ink=B.INK, dark=B.DARK, border=B.BORDER, accent=B.ACCENT, muted=B.MUTED)


def hub_html(meta):
    seed = json.dumps(meta).replace("</", "<\\/")
    brand_name = meta["brand"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(brand_name)} - Monthly Account Review</title>
<style>{HUB_CSS}{H.HEADER_CSS}</style>
</head><body>
{H.head_block(meta, brand_name, logo_b64(), meta.get('marketplace') or '', meta.get('updated_date') or '')}
<main><h2>Monthly Account Reviews</h2><div class="grid" id="cards"></div></main>
{H.footer_html(B.DISCLAIMER, 'one review per month, newest first', brand_name, meta.get('updated_date') or '')}
<script type="application/json" id="hub-seed">{seed}</script>
{H.scripts_block(meta)}
<script>
(function(){{
  var M = JSON.parse(document.getElementById('hub-seed').textContent);
  function e(t){{ var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }}
  function render(){{
    var c = '';
    (M.pages || []).forEach(function(p, i){{
      c += '<a class="card' + (i === 0 ? ' latest' : '') + '" href="' + e(p.file) + '"><b>' + e(p.label) + '</b><span>'
         + e(p.note || 'Open review') + '</span></a>';
    }});
    document.getElementById('cards').innerHTML = c || '<p>No reviews published yet.</p>';
  }}
  render();
  if (location.protocol.indexOf('http') === 0) {{
    fetch('links.json', {{cache: 'no-store'}}).then(function(r){{ return r.ok ? r.json() : null; }})
      .then(function(j){{ if (j && j.pages) {{ M.pages = j.pages; render(); }} }}).catch(function(){{}});
  }}
}})();
</script>
</body></html>
"""


def link_items(marketplace, drive_folder, slack_channel_id):
    sc = "https://sellercentral.amazon.com" if (marketplace or "US") == "US" else None
    return [
        {"key": "drive_folder", "label": "Drive folder", "group": "client",
         "url": f"https://drive.google.com/drive/folders/{drive_folder}" if drive_folder else None},
        {"key": "slack_channel", "label": "Slack channel", "group": "client",
         "url": f"{SLACK_TEAM}/{slack_channel_id}" if slack_channel_id else None},
        {"key": "seller_central", "label": "Seller Central", "group": "client", "url": sc},
        {"key": "ads_console", "label": "Ads console", "group": "client", "url": "https://advertising.amazon.com"},
    ]


def publish(repo, client, brand, month, review, marketplace="US", drive_folder=None,
            slack_channel_id=None, note=None, commit=False, push=False):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        sys.exit("--month must be YYYY-MM")
    slug = folder_slug(client)
    out = os.path.join(repo, "accounts", slug)
    os.makedirs(out, exist_ok=True)
    lj = os.path.join(out, "links.json")
    old = json.load(open(lj)) if os.path.exists(lj) else {}

    page = open(review, encoding="utf-8").read()
    if 'id="xp-home-bar"' not in page:
        bar = ('<div id="xp-home-bar" style="background:#fff;border-bottom:1px solid #e5e5e5;'
               'font:600 12.5px/1 \'Helvetica Neue\',Arial,sans-serif;padding:10px 16px">'
               '<a href="./" style="color:#111;text-decoration:none">&larr; Home &middot; '
               'all monthly reviews</a></div>')
        page = re.sub(r"(<body[^>]*>)", r"\1" + bar.replace("\\", "\\\\"), page, count=1)
    with open(os.path.join(out, f"{month}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    pages = [p for p in old.get("pages", []) if p.get("file") != f"{month}.html"]
    pages.append({"key": month, "file": f"{month}.html", "label": month_label(month),
                  "note": note or "Monthly Account Review"})
    pages.sort(key=lambda p: p["key"], reverse=True)

    items = link_items(marketplace, drive_folder, slack_channel_id)
    prev = {i["key"]: i for i in old.get("items", [])}
    for i in items:
        if not i.get("url") and prev.get(i["key"], {}).get("url"):
            i["url"] = prev[i["key"]]["url"]

    meta = {
        "brand": brand or old.get("brand") or client,
        "client": re.sub(r"^xps-", "", client),
        "slack_channel": "xps-" + re.sub(r"^xps-", "", client),
        "slug": slug,
        "marketplace": marketplace or old.get("marketplace") or "US",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated_date": date.today().isoformat(),
        "items": items, "client_files": [], "pages": pages,
        "names": {"base": f"{brand} - Monthly Account Review"},
    }
    json.dump(meta, open(lj, "w"), indent=2)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(hub_html(meta))

    home = f"{PAGES_BASE}/accounts/{slug}/"
    if commit:
        subprocess.run(["git", "-C", repo, "add", f"accounts/{slug}"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-m", f"{meta['brand']}: monthly review {month}"], check=True)
        if push:
            subprocess.run(["git", "-C", repo, "push"], check=True)
    print(json.dumps({"home": home, "month": home + f"{month}.html", "slug": slug}))
    return home


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--client", required=True, help="Slack channel name, with or without xps-")
    p.add_argument("--brand", required=True)
    p.add_argument("--month", required=True, help="YYYY-MM of the run")
    p.add_argument("--review", required=True, help="the month's review HTML")
    p.add_argument("--marketplace", default="US")
    p.add_argument("--drive-folder")
    p.add_argument("--slack-channel-id")
    p.add_argument("--note")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--push", action="store_true")
    a = p.parse_args()
    publish(a.repo, a.client, a.brand, a.month, a.review, a.marketplace, a.drive_folder,
            a.slack_channel_id, a.note, a.commit, a.push)


if __name__ == "__main__":
    main()
