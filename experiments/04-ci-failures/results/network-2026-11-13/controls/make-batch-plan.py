#!/usr/bin/env python3
"""2026-11-13. Writes the plan of the start-up batch: N pods of each kind (agent, exec-repro, exec-validate, prep) in
three arms, interleaved so that the arms share the same minutes: Kata without the gate, Kata with the gate, runc without
the gate. Each pod probes for 16 s, one try per target every 0.1 s (connect timeout 0.15 s).
usage: make-batch-plan.py <n> <concurrency> > plan.json"""
import json, sys
n, conc = int(sys.argv[1]), int(sys.argv[2]); pods = []
for i in range(1, n + 1):
    for kind, short in (("exec-repro", "exec"), ("agent", "agent"), ("prep", "prep"), ("exec-validate", "val")):
        for rt, gate, arm in (("kata", False, "kn"), ("kata", True, "kg"), ("runc", False, "rn")):
            pods.append({"name": f"b-{short}-{arm}-{i:02d}", "kind": kind, "runtime": rt, "gate": gate, "seconds": 16, "interval": 0.1, "timeout": 0.15})
print(json.dumps({"concurrency": conc, "stagger": 0.3, "pods": pods}))
