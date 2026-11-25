#!/usr/bin/env python3
"""XP Strategy - Performance Overview weekly pull (runs on the XP PC, no Claude tokens).

Pulls the MerchantSpring numbers behind hub/performance.html straight from the MerchantSpring API,
one store and one call at a time, and writes the files tools/build_performance.py reads:

    output/<run date>/ms/<channelId>_W.json     24 weeks (Sun-Sat) through the last Saturday + prior period
    output/<run date>/ms/<channelId>_M.json     last 12 full months + the same 12 months a year earlier
    output/<run date>/ms/<channelId>_MTD.json   1st of the month to yesterday, daily, + the same days of the month before
    output/<run date>/manifest.json             dates for the build (--data-end, --mtd-end) and per-store status

Each file: {"currency": ..., "rows": [{startTime, endTime, sales, priorSales, adSpend, priorAdSpend, adSales, priorAdSales}]}
Vendor stores use ordered revenue as sales (vendorSalesByPeriod), seller stores salesByPeriod with tax excluded.

Usage (from run_performance.ps1, or by hand):
    python perf_pull.py --check          # test the API key and the timezone format with one store, write nothing
    python perf_pull.py                  # full pull
    python perf_pull.py --only 20313310  # one or more stores (comma-separated channelIds)
    python perf_pull.py --today 2026-11-24   # rerun as if it were that day

API key: environment variable MS_API_KEY (preferred) or "api_key" in config.json. Never commit it.
Needs Python 3.9+ and, on Windows, `pip install tzdata` (zoneinfo has no time zone database there).
"""
import argparse, calendar, json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://mm-api.merchantspring.io"
FIELDS = ("startTime", "endTime", "sales", "priorSales", "adSpend", "priorAdSpend", "adSales", "priorAdSales")


def load_config():
    p = os.path.join(HERE, "config.json")
    cfg = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    cfg.setdefault("timezone", "America/Los_Angeles")      # page dates are Pacific
    cfg.setdefault("api_timezone", cfg["timezone"])          # what the API is sent; docs disagree (IANA vs "PST"), --check tells
    cfg.setdefault("stores_file", "performance_stores.json")
    cfg.setdefault("output_dir", "output")
    cfg.setdefault("pause_seconds", 2)                       # between calls; MerchantSpring times out on parallel calls
    cfg.setdefault("retry_wait_seconds", 30)
    cfg.setdefault("tries", 3)
    cfg.setdefault("try_once", ["106902004"])                # BohemiaSkin: returns 400 Invalid channelId
    key = os.environ.get("MS_API_KEY") or cfg.get("api_key")
    if not key:
        sys.exit("No MerchantSpring API key: set MS_API_KEY (MerchantSpring > Settings > API) or api_key in config.json")
    cfg["key"] = key
    return cfg


# ---------- dates ----------
def windows(today):
    """All windows as local dates (inclusive). today = run date in the page time zone."""
    back = (today.weekday() - 5) % 7 or 7                    # most recent Saturday before today
    data_end = today - timedelta(days=back)
    w_from = data_end - timedelta(days=160)                  # 23 weeks, Sunday to Saturday
    w = (w_from, data_end, w_from - timedelta(days=161), w_from - timedelta(days=1))
    last_m_end = today.replace(day=1) - timedelta(days=1)    # last full month
    y, m = last_m_end.year, last_m_end.month - 11
    while m < 1:
        m += 12; y -= 1
    m_from = date(y, m, 1)
    mo = (m_from, last_m_end, m_from.replace(year=m_from.year - 1), last_m_end.replace(year=last_m_end.year - 1,
          day=calendar.monthrange(last_m_end.year - 1, last_m_end.month)[1]))
    mtd_end = today - timedelta(days=1)
    mtd_from = mtd_end.replace(day=1)
    p_last = mtd_from - timedelta(days=1)
    mtd = (mtd_from, mtd_end, p_last.replace(day=1), p_last.replace(day=min(mtd_end.day, p_last.day)))
    return {"data_end": data_end, "W": w, "M": mo, "MTD": mtd}


def epochs(win, tz):
    z = ZoneInfo(tz)
    start = lambda d: int(datetime.combine(d, dtime(0, 0), z).timestamp())
    end = lambda d: int(datetime.combine(d, dtime(23, 59, 59), z).timestamp())
    return {"fromDate": start(win[0]), "toDate": end(win[1]), "priorFromDate": start(win[2]), "priorToDate": end(win[3])}


# ---------- API ----------
class ApiError(Exception):
    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body[:300]}")
        self.code = code


def post(cfg, path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": cfg["key"], "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError) as e:
        raise ApiError(0, str(e))


def by_period(cfg, store, interval, ep):
    body = {"merchantId": store["merchantId"], "channelId": store["channelId"],
            "reportOptions": dict(ep, timezone=cfg["api_timezone"], interval=interval)}
    if store["type"] == "vendor":
        body["marketplaceFilters"] = {"marketplaceType": "amazon", "marketplaceSubtype": "vendor"}
        return post(cfg, "/reports/view/vendorSalesByPeriod", body)
    body["includeTax"] = False
    return post(cfg, "/reports/view/salesByPeriod", body)


def to_file(resp, vendor):
    rows = []
    for r in resp.get("formattedChartData") or []:
        o = {k: r.get(k) for k in FIELDS}
        if vendor:
            o["sales"], o["priorSales"] = r.get("orderedRevenue"), r.get("priorOrderedRevenue")
        rows.append(o)
    return {"currency": resp.get("currency"), "rows": rows}


def call(cfg, store, interval, ep, log):
    tries = 1 if store["channelId"] in cfg["try_once"] else cfg["tries"]
    for i in range(1, tries + 1):
        try:
            resp = by_period(cfg, store, interval, ep)
            if resp.get("status") not in (None, "success"):
                raise ApiError(200, json.dumps(resp)[:300])
            return resp
        except ApiError as e:
            last = e
            log(f"  {store['channelId']} {interval}: try {i}/{tries} failed: {e}")
            if e.code in (401, 403) or i == tries:             # bad key / no access: retrying will not help
                break
            time.sleep(cfg["retry_wait_seconds"])
    raise last


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="test the key and time zone with one store; writes nothing")
    ap.add_argument("--only", help="comma-separated channelIds")
    ap.add_argument("--today", help="run date yyyy-mm-dd (default: today in the page time zone)")
    a = ap.parse_args()
    cfg = load_config()
    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo(cfg["timezone"])).date()
    win = windows(today)
    stores = json.load(open(os.path.join(HERE, cfg["stores_file"]), encoding="utf-8"))["stores"]
    if a.only:
        keep = set(a.only.split(","))
        stores = [s for s in stores if s["channelId"] in keep]
    jobs = [("W", "w"), ("M", "M"), ("MTD", "d")]           # MTD must be daily: interval M returns the whole prior month

    if a.check:
        s = next(x for x in stores if x["type"] == "seller" and x["channelId"] not in cfg["try_once"])
        print("Store:", s["channelId"], "| API time zone:", cfg["api_timezone"])
        chans = post(cfg, "/channels", {})
        print("Key OK:", len(chans) if isinstance(chans, list) else "?", "channels visible")
        ep = epochs(win["MTD"], cfg["timezone"])
        r = to_file(by_period(cfg, s, "d", ep), False)
        tot = sum(float(x["sales"] or 0) for x in r["rows"])
        print(f"Month to date {win['MTD'][0]}..{win['MTD'][1]}: {len(r['rows'])} daily rows, sales {tot:,.2f} {r['currency']}")
        print("If the row count or the total looks wrong, set \"api_timezone\": \"PST\" in config.json and run --check again.")
        return

    out = os.path.join(HERE, cfg["output_dir"], today.isoformat())
    os.makedirs(os.path.join(out, "ms"), exist_ok=True)
    logf = open(os.path.join(out, "pull.log"), "a", encoding="utf-8")
    def log(msg):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line); logf.write(line + "\n"); logf.flush()

    eps = {g: epochs(win[g], cfg["timezone"]) for g, _ in jobs}
    log(f"Run {today}: weekly {win['W'][0]}..{win['W'][1]}, monthly {win['M'][0]}..{win['M'][1]}, "
        f"month to date {win['MTD'][0]}..{win['MTD'][1]} vs {win['MTD'][2]}..{win['MTD'][3]}, {len(stores)} stores")
    status = {}
    for s in stores:
        ch = s["channelId"]; st = status[ch] = {"type": s["type"], "files": {}, "error": None}
        for g, interval in jobs:
            try:
                f = to_file(call(cfg, s, interval, eps[g], log), s["type"] == "vendor")
                json.dump(f, open(os.path.join(out, "ms", f"{ch}_{g}.json"), "w", encoding="utf-8"))
                st["files"][g] = len(f["rows"])
            except ApiError as e:
                st["error"] = f"{g}: {e}"
                break                                          # skip the rest of this store
            finally:
                time.sleep(cfg["pause_seconds"])
        log(f"{ch} ({s['type']}): " + ("SKIPPED " + st["error"] if st["error"] else
            ", ".join(f"{g} {n} rows" for g, n in st["files"].items())))

    # Reconciliation: MerchantSpring's own per-store totals for the last full month and the month to date
    # (salesByChannel, tax excluded, vendor ordered revenue). publish_performance.py compares every store with them.
    lm = win["M"][1]
    checks = {"month": (lm.replace(day=1), lm), "mtd": (win["MTD"][0], win["MTD"][1])}
    for name, (f, t) in checks.items():
        ep = epochs((f, t, f - timedelta(days=1), f - timedelta(days=1)), cfg["timezone"])
        body = dict(ep, timezone=cfg["api_timezone"], includeTax=False, vendorRevenueType="orderedRevenue",
                    pageSize=100, pageIndex=0)
        try:
            rows = []
            while True:                                        # page through every store on the account
                r = post(cfg, "/reports/view/salesByChannel", body)
                got = r.get("rows", [])
                rows += [{"storeId": x.get("storeId"), "store": x.get("store"), "currency": x.get("currency"),
                          "sales": (x.get("sales") or {}).get("value")} for x in got]
                if len(got) < body["pageSize"] or len(rows) >= (r.get("count") or 0):
                    break
                body["pageIndex"] += 1
                time.sleep(cfg["pause_seconds"])
            json.dump({"from": f.isoformat(), "to": t.isoformat(), "rows": rows},
                      open(os.path.join(out, f"check_{name}.json"), "w", encoding="utf-8"))
            log(f"Check totals {name} {f}..{t}: {len(rows)} stores")
        except ApiError as e:
            log(f"Check totals {name}: failed ({e}); publish will skip the reconciliation")
        time.sleep(cfg["pause_seconds"])

    ok = [c for c, v in status.items() if not v["error"]]
    manifest = {
        "run_date": today.isoformat(), "pulled_at": datetime.now().isoformat(timespec="seconds"),
        "data_end": win["data_end"].isoformat(), "mtd_end": win["MTD"][1].isoformat(),
        "windows": {g: [d.isoformat() for d in win[g]] for g, _ in jobs},
        "stores_ok": len(ok), "stores_skipped": {c: v["error"] for c, v in status.items() if v["error"]},
        "stores": status,
        "build": f"python3 tools/build_performance.py --repo . --ms <this folder>/ms --raw <MAP folder> "
                 f"--data-end {win['data_end']} --mtd-end {win['MTD'][1]}",
    }
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"), indent=1)
    log(f"Done: {len(ok)} of {len(stores)} stores OK, {len(stores) - len(ok)} skipped. Output: {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
