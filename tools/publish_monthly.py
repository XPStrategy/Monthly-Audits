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

    python3 tools/publish_monthly.py init --repo . --client xps-<client> --brand "<Brand>" \
        --drive-folder <id> --slack-channel-id <C...>          # empty Home, reserved pages
    python3 tools/publish_monthly.py page --repo . --client xps-<client> --brand "<Brand>" \
        --key amc --label "AMC Analysis" --file amc.html       # replaces the AMC placeholder

Reserved pages (RESERVED_PAGES) get a placeholder at <key>.html so the path exists before
there is content. Prints the Home URL and the month or page URL.
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
.card.off { border-style: dashed; }
.card.off b { color: %(muted)s; }
.empty { font-size: 13.5px; color: %(muted)s; }
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
<main><h2>Monthly Account Reviews</h2><div class="grid" id="cards"></div>
<h2 style="margin-top:34px">Other Pages</h2><div class="grid" id="extra"></div></main>
{H.footer_html(B.DISCLAIMER, 'one review per month, newest first', brand_name, meta.get('updated_date') or '')}
<script type="application/json" id="hub-seed">{seed}</script>
{H.scripts_block(meta)}
<script>
(function(){{
  var M = JSON.parse(document.getElementById('hub-seed').textContent);
  function e(t){{ var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }}
  function render(){{
    var c = '', x = '', first = true;
    (M.pages || []).forEach(function(p){{
      var card = '<a class="card' + (p.status === 'placeholder' ? ' off' : '') + (p.kind !== 'page' && first ? ' latest' : '') + '" href="' + e(p.file) + '"><b>' + e(p.label) + '</b><span>'
         + e(p.note || 'Open') + '</span></a>';
      if (p.kind === 'page') x += card; else {{ c += card; first = false; }}
    }});
    document.getElementById('cards').innerHTML = c || '<p class="empty">No monthly review published yet. The first one lands on the 10th.</p>';
    document.getElementById('extra').innerHTML = x || '<p class="empty">No other pages yet.</p>';
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


# Pages every account gets a fixed path for, even before there is content.
# key -> (label, placeholder note). The file is always <key>.html.
RESERVED_PAGES = {
    "new-to-brand": ("New-to-Brand", "AMC new-to-brand customers and the search terms that bring them"),
    "repeat-purchase": ("Repeat Purchase", "AMC Subscribe & Save, repeat and one-time buyers by month and ASIN"),
    "path-to-conversion": ("Path to Conversion", "AMC ad types buyers saw before purchase, month by month"),
    "time-to-conversion": ("Time to Conversion", "AMC time from ad click to purchase by ad type"),
}
# Monthly reviews shown in the Pages switcher (newest first). Older reviews stay on the Home page.
NAV_MONTHS = 3

# Paths that were used before and are removed from every account on the next init or publish.
RETIRED_FILES = {"amc.html", "amc-ntb.html", "amc-repeat.html", "amc-path.html", "amc-ttc.html"}


def placeholder_html(meta, key, label, note):
    brand_name = meta["brand"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(brand_name)} - {esc(label)}</title>
<style>{HUB_CSS}{H.HEADER_CSS}</style>
</head><body>
{H.head_block(meta, brand_name, logo_b64(), meta.get('marketplace') or '', meta.get('updated_date') or '')}
<main><h2>{esc(label)}</h2>
<p class="empty">{esc(note)}. This page is reserved and has no content yet.</p></main>
{H.footer_html(B.DISCLAIMER, 'not published yet', brand_name, meta.get('updated_date') or '')}
{H.scripts_block(meta)}
</body></html>
"""


def _sort_pages(pages):
    months = sorted([p for p in pages if p.get("kind") != "page"], key=lambda p: p["key"], reverse=True)
    order = list(RESERVED_PAGES)
    extra = sorted([p for p in pages if p.get("kind") == "page"],
                   key=lambda p: (order.index(p["key"]) if p["key"] in order else len(order), p["label"]))
    return months + extra


def write_hub(repo, client, brand, marketplace="US", drive_folder=None, slack_channel_id=None,
              add_pages=(), drop_files=()):
    """Create or refresh accounts/<slug>/ (Home, links.json, reserved placeholders).
    add_pages: page dicts to add or replace (matched by file). Returns (slug, meta)."""
    slug = folder_slug(client)
    out = os.path.join(repo, "accounts", slug)
    os.makedirs(out, exist_ok=True)
    lj = os.path.join(out, "links.json")
    old = json.load(open(lj)) if os.path.exists(lj) else {}
    new_files = {p["file"] for p in add_pages}
    drop = set(drop_files) | RETIRED_FILES
    pages = [p for p in old.get("all_pages", old.get("pages", [])) if p.get("file") not in new_files and p.get("file") not in drop]
    for fn in RETIRED_FILES:
        if os.path.exists(os.path.join(out, fn)):
            os.remove(os.path.join(out, fn))
    pages += list(add_pages)
    have = {p["file"] for p in pages}
    for key, (label, note) in RESERVED_PAGES.items():
        if f"{key}.html" not in have:
            pages.append({"key": key, "file": f"{key}.html", "label": label, "note": "Not published yet",
                          "kind": "page", "status": "placeholder"})
    items = link_items(marketplace, drive_folder, slack_channel_id)
    prev = {i["key"]: i for i in old.get("items", [])}
    for i in items:
        if not i.get("url") and prev.get(i["key"], {}).get("url"):
            i["url"] = prev[i["key"]]["url"]
    brand = brand or old.get("brand") or client
    meta = {
        "brand": brand,
        "client": re.sub(r"^xps-", "", client),
        "slack_channel": "xps-" + re.sub(r"^xps-", "", client),
        "slug": slug,
        "marketplace": marketplace or old.get("marketplace") or "US",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated_date": date.today().isoformat(),
        "items": items, "client_files": [], "pages": _sort_pages(pages),
        "names": {"base": f"{brand} - Monthly Account Review"},
    }
    # links.json "pages" drives the Pages switcher on every page: newest NAV_MONTHS reviews + other pages.
    # The Home page lists everything; the full list is kept in "all_pages".
    nav = [p for p in meta["pages"] if p.get("kind") != "page"][:NAV_MONTHS] + [p for p in meta["pages"] if p.get("kind") == "page"]
    json.dump(dict(meta, pages=nav, all_pages=meta["pages"]), open(lj, "w"), indent=2)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(hub_html(meta))
    for p in meta["pages"]:
        if p.get("status") == "placeholder":
            label, note = RESERVED_PAGES.get(p["key"], (p["label"], p["label"]))
            with open(os.path.join(out, p["file"]), "w") as f:
                f.write(placeholder_html(meta, p["key"], label, note))
    return slug, meta


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

    page = open(review, encoding="utf-8").read()
    if 'id="xp-home-bar"' not in page and 'xph-stick' not in page:   # pages with the shared header get Home from its Pages switcher
        bar = ('<div id="xp-home-bar" style="background:#fff;border-bottom:1px solid #e5e5e5;'
               'font:600 12.5px/1 \'Helvetica Neue\',Arial,sans-serif;padding:10px 16px">'
               '<a href="./" style="color:#111;text-decoration:none">&larr; Home &middot; '
               'all monthly reviews</a></div>')
        page = re.sub(r"(<body[^>]*>)", r"\1" + bar.replace("\\", "\\\\"), page, count=1)
    with open(os.path.join(out, f"{month}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    slug, meta = write_hub(repo, client, brand, marketplace, drive_folder, slack_channel_id,
                           add_pages=[{"key": month, "file": f"{month}.html", "label": month_label(month),
                                       "note": note or "Monthly Account Review", "kind": "review"}])

    home = f"{PAGES_BASE}/accounts/{slug}/"
    if commit:
        subprocess.run(["git", "-C", repo, "add", f"accounts/{slug}"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-m", f"{meta['brand']}: monthly review {month}"], check=True)
        if push:
            subprocess.run(["git", "-C", repo, "push"], check=True)
    print(json.dumps({"home": home, "month": home + f"{month}.html", "slug": slug}))
    return home


def add_page(repo, client, brand, key, label, src, note=None):
    if not re.fullmatch(r"[a-z0-9-]+", key):
        sys.exit("--key: lowercase letters, digits and dashes only")
    slug = folder_slug(client)
    out = os.path.join(repo, "accounts", slug)
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(src, os.path.join(out, f"{key}.html"))
    slug, meta = write_hub(repo, client, brand, add_pages=[{"key": key, "file": f"{key}.html", "label": label,
                                                          "note": note or label, "kind": "page"}])
    print(json.dumps({"page": f"{PAGES_BASE}/accounts/{slug}/{key}.html", "slug": slug}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", nargs="?", default="review", choices=["review", "init", "page"],
                   help="review: publish a month (default) · init: create the account's Home only · page: publish an extra page")
    p.add_argument("--repo", required=True)
    p.add_argument("--client", required=True, help="Slack channel name, with or without xps-")
    p.add_argument("--brand", required=True)
    p.add_argument("--month", help="YYYY-MM of the run (review)")
    p.add_argument("--review", help="the month's review HTML (review)")
    p.add_argument("--key", help="page path key, e.g. amc -> amc.html (page)")
    p.add_argument("--label", help="page card title (page)")
    p.add_argument("--file", help="page HTML (page)")
    p.add_argument("--marketplace", default="US")
    p.add_argument("--drive-folder")
    p.add_argument("--slack-channel-id")
    p.add_argument("--note")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--push", action="store_true")
    a = p.parse_args()
    if a.mode == "init":
        slug, _ = write_hub(a.repo, a.client, a.brand, a.marketplace, a.drive_folder, a.slack_channel_id)
        print(json.dumps({"home": f"{PAGES_BASE}/accounts/{slug}/", "slug": slug}))
        return
    if a.mode == "page":
        if not (a.key and a.label and a.file):
            sys.exit("page needs --key, --label and --file")
        add_page(a.repo, a.client, a.brand, a.key, a.label, a.file, a.note)
        return
    if not (a.month and a.review):
        sys.exit("review needs --month and --review")
    publish(a.repo, a.client, a.brand, a.month, a.review, a.marketplace, a.drive_folder,
            a.slack_channel_id, a.note, a.commit, a.push)


if __name__ == "__main__":
    main()
