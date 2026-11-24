#!/usr/bin/env python3
"""Runs ON aip-ctx-01. Input size of each model call per run, from a saved gateway log (one JSON record per line; in_tok
is the whole input of the call, cache included). Only runs whose calls are in that log appear.
  usage: context_per_run.py <gateway log>        (report/<round>-context-per-run.csv is the output from the header line on)"""
import json, sys, collections
ev=[json.loads(l) for l in open(sys.argv[1]) if l.strip().startswith("{")]
print(dict(collections.Counter(e.get("event", "call") for e in ev)))
calls=[e for e in ev if "in_tok" in e and "run" in e]
print("call events", len(calls), "keys", sorted(calls[0].keys()))
by=collections.defaultdict(list)
for e in calls: by[e["run"]].append(e)
print("run,calls,max_in_tok,median_in_tok,last_in_tok,sum_usd,max_call_usd,calls_over_100k,calls_over_150k")
import statistics as st
for run,cs in sorted(by.items()):
    ins=[c["in_tok"] for c in cs]
    print(",".join(str(x) for x in [run,len(cs),max(ins),round(st.median(ins)),ins[-1],round(sum(c["usd"] for c in cs),4),round(max(c["usd"] for c in cs),4),sum(i>100000 for i in ins),sum(i>150000 for i in ins)]))
