# XP Strategy — Monthly Audits (internal)

Internal Monthly Account Reviews for existing XP Strategy clients, hosted on GitHub Pages.
One link per client; every month's review is added to the same link. XP team only, never sent to clients.

```
build_account_review.py   \
compute_account.py         |  the four review scripts. The xp-monthly-account-review skill
save.py                    |  downloads them from the repo ROOT by name. Never move or rename.
sql_templates.py          /
tools/publish_monthly.py   publishes one client's month into accounts/
accounts/<client>-<8 hex>/
  index.html               Home: one card per month, newest first (the link the AM opens)
  <yyyy-mm>.html           that month's review
  amc.html                 AMC Analysis (reserved: placeholder until published)
  links.json               months + links (Drive folder, Slack channel, consoles)
index.html                 blank landing page, lists nothing
robots.txt                 Disallow: /
```

`<client>` = the Slack channel name without `xps-` (`xps-cosmo-technologies` → `cosmo-technologies`).
The 8-hex suffix is fixed per client, so the link never changes.

## Where things live

| What | Where |
| --- | --- |
| Client folders | Google Drive: [XP Strategy - Internal Audits](https://drive.google.com/drive/folders/1dZfLdn8jovhQv2T8HOyx-WqoPHHJRgRT), one folder per `#xps-<client>` Slack channel, each with `Source` (run files by month) and `Old` |
| Channel ↔ folder ↔ MAP account map | `_Channel Map - Internal Audits` sheet in that Drive folder |
| Live pages | `https://xpstrategy.github.io/Monthly-Audits/accounts/<client>-<8 hex>/` |
| Communication | The client's own `#xps-<client>` Slack channel only. Claude drafts the post; a person approves before it sends |

## Every account already has a Home

All 29 `#xps-` channels have `accounts/<client>-<8 hex>/` with a Home page and an AMC placeholder,
even before their first review. The Drive folder holds `[LINK] <Brand> - XP Strategy - Internal Audit Page`
with the paths.

- New account: `python3 tools/publish_monthly.py init --repo . --client xps-<client> --brand "<Brand>" --drive-folder <id> --slack-channel-id <id>`
- Extra page (AMC or any other): `python3 tools/publish_monthly.py page --repo . --client xps-<client> --brand "<Brand>" --key amc --label "AMC Analysis" --file amc.html`
  The page appears under "Other Pages" on Home and in every page's Pages switcher. To reserve a new path
  for every account, add it to `RESERVED_PAGES` in the script and re-run `init`.

## Monthly run (10th of each month)

1. Run `xp-monthly-account-review` for the account (MAP data, no manual input).
2. Publish: `python3 tools/publish_monthly.py --repo . --client <client> --brand "<Brand>" --month <yyyy-mm> --review <html> --drive-folder <id> --slack-channel-id <id> --commit --push`
3. Save the run files (`config.json`, `findings.json`, MAP results) in the client's Drive folder `Source/<yyyy-mm>`.
4. Draft the `#xps-<client>` post (alert counts, lead alert, Home link); send after approval.

## Visibility

GitHub Pages is public to anyone holding a link, including for this public repo. Protection: fixed
random suffix per client, `noindex` on every page, `robots.txt`, a root page that lists nothing.
The Drive and Slack links on a page still need an XP login. Never put notes about people,
pricing or credentials in a page or `links.json`. Raw MAP data stays in Drive.

## One-time setup

Settings → Pages → Source: Deploy from a branch, `main`, `/ (root)`. Needs a repo admin (CEO).
