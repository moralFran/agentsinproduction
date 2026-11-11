#!/usr/bin/env python3
"""Counts results per (runtime, probe, phase) from a JSONL of probe attempts."""
import collections, json, sys
c = collections.defaultdict(collections.Counter)
for l in open(sys.argv[1]):
    r = json.loads(l); c[(r["runtime"], r["probe"], r["phase"])][r["result"]] += 1
for k in sorted(c, key=lambda k: (k[0], k[1], k[2])):
    print(f"{k[0]:10} {k[1]:18} {k[2]:10} " + ", ".join(f"{v}× {n}" for n, v in c[k].most_common()))
