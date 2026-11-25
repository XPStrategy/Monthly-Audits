#!/usr/bin/env python3
"""Build hub/performance.html from a PC pull bundle and check it before it is pushed.

The weekly MerchantSpring pull runs on the XP PC (pc/xp_performance/run_performance.ps1, no Claude tokens) and
leaves C:\\XP\\xp_performance\\output\\<run date>\\ (or perf_bundle_<run date>.zip). This script is the only step
left for the publish run:

    python3 tools/publish_performance.py --repo . --bundle <folder or zip> [--raw <Badass Moto MAP folder>]

It reads manifest.json for the dates, builds the page (build_master + build_performance with --data-end and
--mtd-end), then checks:
  1. every MerchantSpring account on the page has a last-full-month value and a month-to-date value
  2. the latest week on the page ends on the manifest's data_end
  3. every store's last-month and month-to-date sales match MerchantSpring's own per-store totals
     (check_month.json / check_mtd.json from the same pull) within 1%
Exit code 0 = safe to commit hub/performance.html and hub/index.html; 1 = do not publish (reasons printed).
The bundle stays outside the repo: never commit raw data.
"""
import argparse, json, os, shutil, sys, tempfile, zipfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_master as M        # noqa: E402
import build_performance as BP  # noqa: E402

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--bundle", required=True, help="run folder (with manifest.json and ms/) or perf_bundle_<date>.zip")
    ap.add_argument("--raw", help="MAP folder for accounts not in MerchantSpring (Badass Moto); optional")
    ap.add_argument("--tolerance", type=float, default=0.01)
    a = ap.parse_args()

    tmp = None
    bundle = a.bundle
    if bundle.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="perf_bundle_")
        with zipfile.ZipFile(bundle) as z:
            for n in z.namelist():                       # plain relative names only
                if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/"):
                    sys.exit(f"Refusing bundle entry {n!r}")
            z.extractall(tmp)
        bundle = tmp
    try:
        man = json.load(open(os.path.join(bundle, "manifest.json"), encoding="utf-8"))
        msdir = os.path.join(bundle, "ms")
        raw = a.raw or tempfile.mkdtemp(prefix="perf_raw_")
        data_end, mtd_end = date.fromisoformat(man["data_end"]), date.fromisoformat(man["mtd_end"])
        print(f"Bundle {man['run_date']}: data through {data_end}, month to date through {mtd_end}, "
              f"{man['stores_ok']} stores OK, skipped: {man['stores_skipped'] or 'none'}")

        M.build(a.repo) if hasattr(M, "build") else os.system(f'python3 "{os.path.join(a.repo, "tools", "build_master.py")}" --repo "{a.repo}"')
        p, rows = BP.build(a.repo, raw, data_end, msdir, mtd_end)
        print("[done]", p)

        fails, notes = [], []
        last_month = man["windows"]["M"][1][:7]
        week_key = (data_end - timedelta(days=6)).isoformat()
        for r in rows:
            if r.get("src") != "MerchantSpring":
                continue
            s = r["s"]
            if not any(x["k"] == last_month and x["ts"] is not None for x in s["M"]):
                fails.append(f"{r['brand']}: no {last_month} value")
            if not s.get("MTD") or s["MTD"]["cur"]["ts"] is None:
                notes.append(f"{r['brand']}: no month-to-date sales") if s.get("MTD") else fails.append(f"{r['brand']}: no month-to-date data")
            if not s["W"] or s["W"][-1]["k"] != week_key:
                fails.append(f"{r['brand']}: latest week {s['W'][-1]['k'] if s['W'] else None}, expected {week_key}")

        # store-level reconciliation against MerchantSpring's per-store totals (USD stores only: salesByChannel is USD)
        y, m = int(last_month[:4]), int(last_month[5:])
        mlabel = f"{MON[m - 1]} {y}"
        for name, label in (("month", mlabel), ("mtd", "month to date")):
            f = os.path.join(bundle, f"check_{name}.json")
            if not os.path.exists(f):
                notes.append(f"no check_{name}.json in the bundle: {label} reconciliation skipped")
                continue
            ref = {str(x["storeId"]): x for x in json.load(open(f, encoding="utf-8"))["rows"]}
            n = 0
            for ch in man["stores"]:
                g = "M" if name == "month" else "MTD"
                fp = os.path.join(msdir, f"{ch}_{g}.json")
                if not os.path.exists(fp) or ch not in ref:
                    continue
                d = json.load(open(fp, encoding="utf-8"))
                if d.get("currency") != "USD" or ref[ch].get("currency") not in (None, "USD"):
                    continue
                mine = (sum(num(x["sales"]) for x in d["rows"]) if g == "MTD"
                        else sum(num(x["sales"]) for x in d["rows"] if x["startTime"] == mlabel))
                theirs = num(ref[ch]["sales"]); n += 1
                if abs(mine - theirs) > a.tolerance * max(abs(theirs), 1.0) and abs(mine - theirs) > 5:
                    fails.append(f"store {ch} {label}: pulled {mine:,.2f} vs MerchantSpring total {theirs:,.2f}")
            print(f"Reconciled {n} stores for {label}")

        for x in notes:
            print("NOTE:", x)
        if fails:
            print("DO NOT PUBLISH:")
            for x in fails:
                print("  -", x)
            sys.exit(1)
        print(f"OK to publish: commit hub/performance.html and hub/index.html as "
              f"\"Performance Overview: weekly refresh through {data_end} (MTD through {mtd_end})\"")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
