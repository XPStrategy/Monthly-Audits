#!/usr/bin/env python3
"""Pull a completed get_amc_query_result payload out of a Claude session transcript (.jsonl)
and save its rows as JSON, so results never need retyping.

Usage: python3 tools/amc_from_transcript.py <transcript.jsonl> <query_id> <out.json>
"""
import json, sys


def walk(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)
    elif isinstance(o, str):
        yield o


def main(tr, qid, out):
    best = None
    for line in open(tr):
        if qid not in line:
            continue
        for s in walk(json.loads(line)):
            if qid in s and '"rows"' in s and '"completed"' in s:
                try:
                    j = json.loads(s)
                except Exception:
                    i = s.find("{"); j = json.loads(s[i:s.rfind("}") + 1])
                if j.get("query_id") == qid and j.get("rows") is not None:
                    best = j
    if not best:
        sys.exit(f"no completed result for {qid}")
    json.dump(best["rows"], open(out, "w"))
    print(out, len(best["rows"]), "rows", "(truncated)" if best.get("truncated") else "")


if __name__ == "__main__":
    main(*sys.argv[1:4])
