#!/usr/bin/env python3
"""Runs ON aip-ctx-01 (experiment 06, criteria E9/E10). The live attempts ran with VALIDATE=0 and cases/validate.py ran
later on the saved patches. This puts each saved verdict into the journal's `validator` field, the same way
attempt_team.sh does when it validates in line (no `samples`, plus `n_samples`). The journal as it was is copied first to
results/attempts-<round>.before-verdicts-<UTC time>.jsonl. A journal line whose verdict file is missing is left as it is.
Running it again changes nothing.        usage: merge_verdicts.py <round>"""
import json, os, shutil, sys, time

rnd = sys.argv[1]; jp = f"results/attempts-{rnd}.jsonl"; pd = f"results/patches/{rnd}"
rows = [json.loads(l) for l in open(jp) if l.strip()]
out, changed = [], 0
for r in rows:
    vf = f"{pd}/{r['run']}.verdict.json"
    if os.path.exists(vf):
        ex = json.load(open(vf))
        ex = {k: v for k, v in ex.items() if k != "samples"} | ({"n_samples": len(ex["samples"])} if isinstance(ex.get("samples"), list) else {})
        if r.get("validator") != ex: r = r | {"validator": ex}; changed += 1
    out.append(r)
if changed:
    shutil.copy2(jp, f"results/attempts-{rnd}.before-verdicts-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl")
    tmp = jp + ".tmp"
    with open(tmp, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in out)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, jp)
for r in out: print(r["run"], r["config"], r["validator"].get("outcome"), str(r["validator"].get("why", ""))[:120])
print(f"{changed} journal line(s) updated")
