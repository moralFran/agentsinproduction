#!/usr/bin/env python3
"""Median and observed range of start time and idle memory per runtime, from perf.jsonl. Failures listed apart."""
import collections, json, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
by = collections.defaultdict(list)
for r in rows: by[r["runtime"]].append(r)
med = {}
for rt, rs in sorted(by.items()):
    ok = [r for r in rs if r["outcome"] == "ok"]; bad = [r for r in rs if r["outcome"] != "ok"]
    s = [r["start_ms"] for r in ok]; m = [r["pss_kb_total"] / 1024 for r in ok]
    med[rt] = (st.median(s), st.median(m))
    print(f"{rt:10} starts ok {len(ok)}/{len(rs)}  failures {len(bad)}")
    print(f"           start ms: median {st.median(s):.0f}  range {min(s)}-{max(s)}")
    print(f"           PSS MiB:  median {st.median(m):.1f}  range {min(m):.1f}-{max(m):.1f}")
    parts = collections.defaultdict(list)
    for r in ok:
        for k, v in r["pss_kb_by_process"].items(): parts[k].append(v / 1024)
    print("           by process (median MiB): " + ", ".join(f"{k} {st.median(v):.1f}" for k, v in sorted(parts.items())))
if len(med) == 2:
    print(f"START_DELTA_MS = {med['kata-qemu'][0] - med['runc'][0]:.0f}   MEM_DELTA_MIB = {med['kata-qemu'][1] - med['runc'][1]:.1f}")
