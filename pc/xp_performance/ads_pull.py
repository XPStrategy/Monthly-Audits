#!/usr/bin/env python3
r"""XP Strategy - Performance Overview: Amazon Ads API pull for the ad columns (runs on the XP PC, no Claude tokens).

Ad Spend and Ad Sales per hub account per day, from the Amazon Ads reporting API (v3), Sponsored Products +
Sponsored Brands + Sponsored Display, with the same API credentials as xp_budget_bot / xp_change_audit.
Total Sales still comes from MerchantSpring (pulled by Claude at publish time).

Amazon keeps campaign report data for a limited time (about 95 days for SP, 60 for SB, 65 for SD), so this
script keeps its own history: every run re-pulls the last `lookback_days` (default 60) and merges them into
history/ads_daily.json. Older periods on the page keep the values already published.

    python ads_pull.py --profiles            # list every profile the credentials can see (to fill config_ads.json)
    python ads_pull.py --check               # token + one small SP report for the first account; writes nothing
    python ads_pull.py                       # full pull -> output/<run date>/ads_daily.json + history merge
    python ads_pull.py --only boroux,displate --days 14

Output (output/<run date>/ads_daily.json and history/ads_daily.json):
    {"attribution": "14d", "accounts": {"<hub client>": {"currency": "USD",
        "days": {"2026-11-23": {"sp": 224.41, "asl": 1505.0, "SP": [cost, sales], "SB": [...], "SD": [...]}}}}}
Accounts that share a hub client (e.g. Ultimate Footwear US + vendor profile) are added together.

Config: credentials and US accounts are read from the budget bot (C:\XP\xp_budget_bot\config.json: "amazon" block and
"accounts" name -> profile ids). Optional config_ads.json for settings, extra accounts (UK, accounts not in the bot) and
"skip_clients". Env vars ADS_CLIENT_ID / ADS_CLIENT_SECRET / ADS_REFRESH_TOKEN override. Never commit the output.
"""
import argparse, gzip, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTS = {"NA": "https://advertising-api.amazon.com", "EU": "https://advertising-api-eu.amazon.com",
         "FE": "https://advertising-api-fe.amazon.com"}
TOKEN_URL = "https://api.amazon.com/auth/o2/token"
# report definitions per ad product; "sales" column depends on the attribution setting for SP only
PRODUCTS = {
    "SP": {"adProduct": "SPONSORED_PRODUCTS", "reportTypeId": "spCampaigns", "sales": {"7d": "sales7d", "14d": "sales14d"}},
    "SB": {"adProduct": "SPONSORED_BRANDS", "reportTypeId": "sbCampaigns", "sales": {"7d": "sales", "14d": "sales"}},
    "SD": {"adProduct": "SPONSORED_DISPLAY", "reportTypeId": "sdCampaigns", "sales": {"7d": "sales", "14d": "sales"}},
}
RETENTION = {"SP": 95, "SB": 60, "SD": 65}


# Budget bot account name -> hub client (same map as tools/build_changes.py NAME_TO_CLIENT).
NAME_TO_CLIENT = {
    "Advanced Bionutritionals": "advanced-bionutritionals", "Badass Moto": "badass-moto", "Bingo": "bingo1525",
    "Cosmo": "cosmo-technologies", "DEZINE": "dzg-products", "Displate": "displate", "Inglesina": "inglesina",
    "Joe's Trends": "joes-trend", "Kensington": "kensingtonvalleytrading", "Kitchen Globe": "boroux",
    "Leading Choice": "leading-choice-products", "Nutrivein": "nutrivein", "Reliable Home": "md-buildingproducts",
    "SavonGoods": "savongoods", "Shine Water": "shinewater", "SkySail": "skysailconsumer",
    "Smart Cookie": "smart-cookie", "Spring Mount": "spring-mount-supply", "Steam Clip": "steam-clip",
    "TrailHeads": "trailheads-apparel", "TurmSkin": "turmskin", "Ultimate Footwear": "ultimate-footwear",
    "Ultimate Washer": "ultimate-washer", "VersaGroup": "versa-group",
}
DEFAULT_BOT_CONFIG = r"C:\XP\xp_budget_bot\config.json"


def load_config():
    """Credentials and US accounts come from the budget bot's config.json (nothing copied, nothing stored twice).
    config_ads.json is optional: settings, extra accounts not in the budget bot (e.g. UK), or "skip"."""
    p = os.path.join(HERE, "config_ads.json")
    cfg = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    extra = cfg.get("accounts", [])
    bot_path = cfg.get("budget_bot_config", DEFAULT_BOT_CONFIG)
    bot = json.load(open(bot_path, encoding="utf-8")) if os.path.exists(bot_path) else {}
    am = bot.get("amazon", {})
    if bot:
        accts = []
        for name, ids in bot.get("accounts", {}).items():
            client = NAME_TO_CLIENT.get(name)
            if not client:
                print(f"note: budget bot account {name!r} has no hub client mapping; skipped")
                continue
            for pid in (ids if isinstance(ids, list) else [ids]):
                accts.append({"name": name, "client": client, "profile_id": str(pid),
                              "region": am.get("region", "NA"), "currency": "USD"})
        have = {a["profile_id"] for a in accts}
        cfg["accounts"] = accts + [a for a in extra if str(a.get("profile_id")) not in have]
    elif not extra:
        sys.exit(f"No budget bot config at {bot_path} and no accounts in config_ads.json")
    skip = set(cfg.get("skip_clients", []))
    cfg["accounts"] = [a for a in cfg["accounts"] if a["client"] not in skip]
    lwa = cfg.get("lwa") or {}
    for k, env in (("client_id", "ADS_CLIENT_ID"), ("client_secret", "ADS_CLIENT_SECRET"), ("refresh_token", "ADS_REFRESH_TOKEN")):
        cfg[k] = os.environ.get(env) or lwa.get(k) or am.get(k)   # env var, then config_ads.json, then the budget bot
    if not all((cfg["client_id"], cfg["client_secret"], cfg["refresh_token"])):
        sys.exit(f"Missing Amazon Ads API credentials. Budget bot config {'found' if bot else 'NOT found'} at {bot_path}"
                 f"{' but its amazon block is incomplete' if bot else ''}. Fix the path with \"budget_bot_config\" in config_ads.json.")
    print(f"Credentials: {'budget bot config ' + bot_path if bot and not lwa.get('client_id') else 'config_ads.json / environment'}; "
          f"{len(cfg['accounts'])} account profiles")
    cfg.setdefault("timezone", "America/Los_Angeles")
    cfg.setdefault("attribution", "14d")          # SP sales window; SB / SD always report 14-day sales
    cfg.setdefault("lookback_days", 60)
    cfg.setdefault("products", ["SP", "SB", "SD"])
    cfg.setdefault("poll_seconds", 20)
    cfg.setdefault("max_wait_minutes", 45)
    return cfg


# ---------- HTTP ----------
class Api:
    def __init__(self, cfg):
        self.cfg, self.token, self.exp = cfg, None, 0

    def access_token(self):
        if self.token and time.time() < self.exp - 120:
            return self.token
        data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": self.cfg["refresh_token"],
                                       "client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"]}).encode()
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data, method="POST"), timeout=60) as r:
            t = json.loads(r.read().decode())
        self.token, self.exp = t["access_token"], time.time() + int(t.get("expires_in", 3600))
        return self.token

    def req(self, method, url, profile=None, body=None, ctype=None, tries=5):
        for i in range(tries):
            h = {"Authorization": "Bearer " + self.access_token(), "Amazon-Advertising-API-ClientId": self.cfg["client_id"],
                 "Accept": "application/json"}
            if profile:
                h["Amazon-Advertising-API-Scope"] = str(profile)
            if body is not None:
                h["Content-Type"] = ctype or "application/json"
            r = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
            try:
                with urllib.request.urlopen(r, timeout=120) as resp:
                    return resp.status, json.loads(resp.read().decode() or "null")
            except urllib.error.HTTPError as e:
                txt = e.read().decode("utf-8", "replace")
                if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                    time.sleep(int(e.headers.get("Retry-After") or 0) or 15 * (i + 1)); continue
                return e.code, txt
        return 0, "no response"


def download(url):
    with urllib.request.urlopen(url, timeout=300) as r:      # pre-signed S3 url: no auth headers
        raw = r.read()
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass
    return json.loads(raw.decode("utf-8"))


# ---------- reports ----------
def chunks(start, end, size=31):
    d = start
    while d <= end:
        e = min(end, d + timedelta(days=size - 1))
        yield d, e
        d = e + timedelta(days=1)


def create_report(api, acct, prod, start, end, attribution):
    p = PRODUCTS[prod]
    body = {"name": f"xp-perf {prod} {start}..{end}", "startDate": start.isoformat(), "endDate": end.isoformat(),
            "configuration": {"adProduct": p["adProduct"], "groupBy": ["campaign"], "reportTypeId": p["reportTypeId"],
                              "columns": ["date", "cost", p["sales"][attribution]], "timeUnit": "DAILY", "format": "GZIP_JSON"}}
    code, r = api.req("POST", HOSTS[acct.get("region", "NA")] + "/reporting/reports", acct["profile_id"], body,
                      "application/vnd.createasyncreportrequest.v3+json")
    if code in (200, 202) and isinstance(r, dict) and r.get("reportId"):
        return r["reportId"], None
    if code == 425 and "duplicate" in str(r).lower():           # same report already requested: reuse it
        rid = str(r).rsplit(":", 1)[-1].strip().strip('"}').strip()
        return rid, None
    return None, f"HTTP {code}: {str(r)[:200]}"


def wait_report(api, acct, rid, deadline, poll, verbose=False):
    t0 = time.time()
    while time.time() < deadline:
        code, r = api.req("GET", HOSTS[acct.get("region", "NA")] + f"/reporting/reports/{rid}", acct["profile_id"])
        if verbose:
            print(f"  report {r.get('status') if isinstance(r, dict) else code} after {int(time.time() - t0)}s", flush=True)
        if code == 200 and isinstance(r, dict):
            if r.get("status") == "COMPLETED":
                return r.get("url"), None
            if r.get("status") == "FAILED":
                return None, "report FAILED: " + str(r.get("failureReason"))[:200]
        elif code not in (200,):
            return None, f"HTTP {code}: {str(r)[:200]}"
        time.sleep(poll)
    return None, "timed out waiting for the report"


# ---------- main ----------
def list_profiles(api):
    for region, host in HOSTS.items():
        code, r = api.req("GET", host + "/v2/profiles")
        if code != 200 or not isinstance(r, list):
            print(f"{region}: HTTP {code}"); continue
        for p in r:
            ai = p.get("accountInfo", {})
            print(f"{region}\t{p.get('profileId')}\t{p.get('countryCode')}\t{p.get('currencyCode')}\t{ai.get('type')}\t{ai.get('name')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", help="comma-separated hub clients")
    ap.add_argument("--days", type=int, help="override lookback_days")
    ap.add_argument("--today", help="run date yyyy-mm-dd (default today, page time zone)")
    a = ap.parse_args()
    cfg = load_config()
    api = Api(cfg)
    if a.profiles:
        list_profiles(api); return

    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo(cfg["timezone"])).date()
    end = today - timedelta(days=1)
    accts = [x for x in cfg["accounts"] if x.get("profile_id") and not x.get("skip")]
    if a.only:
        keep = set(a.only.split(","))
        accts = [x for x in accts if x["client"] in keep]

    if a.check:
        acct = accts[0]
        print("Token OK" if api.access_token() else "Token failed", flush=True)
        rid, err = create_report(api, acct, "SP", end - timedelta(days=2), end, cfg["attribution"])
        if err:
            sys.exit(f"{acct['name']}: could not create a report: {err}")
        print(f"{acct['name']}: report requested ({rid}); Amazon usually takes 1-10 minutes", flush=True)
        url, err = wait_report(api, acct, rid, time.time() + 15 * 60, cfg["poll_seconds"], verbose=True)
        if err:
            sys.exit(f"{acct['name']}: {err}")
        rows = download(url)
        sc = PRODUCTS["SP"]["sales"][cfg["attribution"]]
        print(f"{acct['name']} SP {end - timedelta(days=2)}..{end}: {len(rows)} campaign-days, "
              f"cost {sum(r.get('cost') or 0 for r in rows):,.2f}, sales {sum(r.get(sc) or 0 for r in rows):,.2f}")
        return

    out = os.path.join(HERE, "output", today.isoformat())
    os.makedirs(out, exist_ok=True)
    logf = open(os.path.join(out, "ads_pull.log"), "a", encoding="utf-8")
    def log(m):
        line = f"{datetime.now():%H:%M:%S} {m}"; print(line); logf.write(line + "\n"); logf.flush()

    lookback = a.days or cfg["lookback_days"]
    log(f"Ads pull {today}: {len(accts)} accounts, {lookback} days through {end}, SP attribution {cfg['attribution']}")
    # 1) request every report first (they run in parallel on Amazon's side), 2) collect them
    jobs, errors = [], {}
    for acct in accts:
        for prod in cfg["products"]:
            start = max(end - timedelta(days=lookback - 1), end - timedelta(days=RETENTION[prod] - 2))
            for s, e in chunks(start, end):
                rid, err = create_report(api, acct, prod, s, e, cfg["attribution"])
                if err:
                    errors.setdefault(acct["client"], []).append(f"{prod} {s}..{e}: {err}")
                    log(f"  {acct['name']} {prod} {s}..{e}: {err}")
                else:
                    jobs.append((acct, prod, s, e, rid))
                time.sleep(1)
    log(f"Requested {len(jobs)} reports; waiting")
    deadline = time.time() + cfg["max_wait_minutes"] * 60
    res = {}
    for acct, prod, s, e, rid in jobs:
        url, err = wait_report(api, acct, rid, deadline, cfg["poll_seconds"])
        if err:
            errors.setdefault(acct["client"], []).append(f"{prod} {s}..{e}: {err}"); log(f"  {acct['name']} {prod} {s}..{e}: {err}")
            continue
        sc = PRODUCTS[prod]["sales"][cfg["attribution"]]
        c = res.setdefault(acct["client"], {"currency": acct.get("currency", "USD"), "days": {}})
        for r in download(url):
            d = c["days"].setdefault(r["date"], {"sp": 0.0, "asl": 0.0})
            d["sp"] += r.get("cost") or 0; d["asl"] += r.get(sc) or 0
            pr = d.setdefault(prod, [0.0, 0.0]); pr[0] += r.get("cost") or 0; pr[1] += r.get(sc) or 0
        log(f"  {acct['name']} {prod} {s}..{e}: done")
    for c in res.values():                                  # round once at the end
        for d in c["days"].values():
            for k, v in list(d.items()):
                d[k] = round(v, 2) if isinstance(v, float) else [round(x, 2) for x in v]

    meta = {"run_date": today.isoformat(), "end": end.isoformat(), "lookback_days": lookback,
            "attribution": cfg["attribution"], "errors": errors}
    json.dump(dict(meta, accounts=res), open(os.path.join(out, "ads_daily.json"), "w", encoding="utf-8"))
    # merge into the local history (newer pull wins for the days it covers)
    hp = os.path.join(HERE, "history", "ads_daily.json")
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {"accounts": {}}
    for client, c in res.items():
        if client in errors:                               # partial pull (a product or a chunk failed): keep the old history
            log(f"  history not updated for {client}: {errors[client][0]}")
            continue
        h = hist["accounts"].setdefault(client, {"currency": c["currency"], "days": {}})
        h["days"].update(c["days"])
    hist.update(attribution=cfg["attribution"], updated=today.isoformat())
    json.dump(hist, open(hp, "w", encoding="utf-8"))
    log(f"Done: {len(res)} accounts with data, {len(errors)} with errors. Output {out}; history {hp}")
    sys.exit(0 if res else 1)


if __name__ == "__main__":
    main()
