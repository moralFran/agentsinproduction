#!/usr/bin/env python3
"""One line per attempt from a task JSONL, then valid patches and median task time per runtime."""
import collections, json, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
print(f"{'RUN':13} {'OUTCOME':9} {'CALLS':>5} {'TASK s':>7} {'TOOLS s':>8}  VALID")
by = collections.defaultdict(list)
for r in sorted(rows, key=lambda r: (r["runtime"], r["i"])):
    a, v = r["agent"], r["validation"]; by[r["runtime"]].append(r)
    print(f"{a.get('run', r.get('run', '?')):13} {a.get('outcome', '?'):9} {a.get('model_calls', 0):>5} {a.get('total_s', 0):>7.1f} {a.get('tool_s', 0):>8.1f}  {'yes' if v.get('valid') else 'NO'}")
for rt, rs in sorted(by.items()):
    print(f"{rt:10} valid {sum(1 for r in rs if r['validation'].get('valid'))}/{len(rs)}   median task {st.median(r['agent'].get('total_s', 0) for r in rs):.1f} s")
