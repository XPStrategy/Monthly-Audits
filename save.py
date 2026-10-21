#!/usr/bin/env python3
"""save.py <account_dir> name=<tool-result id> ...
Copy MAP results that overflowed to saved tool-result files into an account folder,
strip the pad column, normalise analyst output, and report row count + truncation."""
import glob, json, os, sys
acct = sys.argv[1]; os.makedirs(acct, exist_ok=True)
files = glob.glob(os.path.expanduser("~/.claude/projects/*/tool-results/*")) + glob.glob("/root/.claude/projects/*/tool-results/*")
for pair in sys.argv[2:]:
    name, rid = pair.split("=")
    src = next((f for f in sorted(set(files), key=os.path.getmtime, reverse=True) if rid in os.path.basename(f)), None)
    if not src:
        print(name, "MISSING", rid); continue
    d = json.load(open(src))
    if "data" in d and "status" not in d:
        d = {"status": "success", "data": d["data"], "truncated": d.get("truncated")}
    for r in d.get("data", []):
        r.pop("pad", None)
    json.dump(d, open(os.path.join(acct, name + ".json"), "w"))
    print(f"{name:13} rows={len(d.get('data', [])):5} truncated={d.get('truncated')}")
