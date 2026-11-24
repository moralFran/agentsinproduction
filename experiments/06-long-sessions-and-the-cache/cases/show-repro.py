#!/usr/bin/env python3
"""Prints one reproduction (the last line of a repro JSONL) as six short lines: three runs per tree."""
import json, sys
r = json.loads(open(sys.argv[1]).read().strip().splitlines()[-1])
for tree in ("broken", "fixed"):
    for i, x in enumerate(r[tree].get("runs", []), 1):
        print(f"{tree:7} run {i}  {'PASS' if x['rc'] == 0 else 'FAIL'}  ({x['s']:.0f} s)")
print(f"verdict: {r['verdict']}")
