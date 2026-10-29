#!/usr/bin/env python3
"""Merge saved paged_query_result outputs for one result_id into a single JSON row list.
Pages may overlap or arrive in any order; each saved page records its offset.

Usage: python3 tools/amc_merge_pages.py <tool-results dir> <result_id> <out.json>
"""
import glob, json, os, sys


def main(d, rid, out):
    rows = {}; total = None
    for p in glob.glob(os.path.join(d, "*paged_query_result*.txt")):
        try:
            j = json.load(open(p))
        except Exception:
            continue
        if j.get("result_id") != rid:
            continue
        total = j.get("total_row_count", total)
        for i, r in enumerate(j["rows"]):
            rows[j["offset"] + i] = r
    if total is not None and len(rows) != total:
        sys.exit(f"incomplete: {len(rows)} of {total} rows; missing offsets e.g. {[i for i in range(total) if i not in rows][:5]}")
    json.dump([rows[i] for i in sorted(rows)], open(out, "w"))
    print(out, len(rows), "rows")


if __name__ == "__main__":
    main(*sys.argv[1:4])
