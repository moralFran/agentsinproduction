#!/usr/bin/env python3
"""Capture helper (c25), runs on the Mac in the results folder and counts from the saved raw files of 2026-11-13:
1. start-up batch (raw/main/batch, 180 pods): in how many pods did the main container establish a connection to a
   destination its policy forbids (socket ESTABLISHED) during its 16 s, per arm;
2. the 12 long-running pods of raw/main (steady, steady2), after each pod's first 5 s (the two T3 pods: after the policy
   was applied + 5 s): forbidden tries, and how many connections the node let through to a forbidden destination
   (conntrack NEW events from the pod's address to an address the pod's policy does not allow, in that time).
usage: python3 capture/tally.py"""
import collections, glob, gzip, json, re
op = lambda p: gzip.open(p, "rt", errors="replace") if p.endswith(".gz") else open(p, errors="replace")
logs = lambda pat: sorted(glob.glob(pat) + glob.glob(pat + ".gz"))
arm = collections.defaultdict(lambda: [0, 0])
for p in logs("raw/main/batch/b-*.log"):
    if ".init-" in p: continue
    m = re.search(r"b-\w+-(kn|kg|rn)-\d+", p); hit = False; allowed = set()
    for l in op(p):
        if l.startswith("H "): allowed = set(json.loads(l[2:])["allowed"])
        elif l.startswith("A "):
            f = l.split()
            if f[2] not in allowed and f[3] == "o" and f[6] == "st=1": hit = True
    arm[m.group(1)][0] += 1; arm[m.group(1)][1] += hit
print("start-up batch: pods whose main container reached a forbidden destination")
for k, name in (("kn", "Kata, no gate"), ("kg", "Kata, with gate"), ("rn", "runc, no gate")): print(f"  {name:<16}{arm[k][1]:3d} of {arm[k][0]}")
t3 = {}
for l in open("raw/main/t3-steady-apply.jsonl"):
    j = json.loads(l)
    for p in j["pods"].split(): t3[p] = j["apply_end_ms"]
pods = {}; tries = collections.Counter()
for p in logs("raw/main/steady*/*.log"):
    h = None
    for l in op(p):
        if l.startswith("H "):
            h = json.loads(l[2:]); start = t3.get(h["pod"], h["t0_epoch_ms"]) + 5000; allowed = set(h["allowed"])
            pods[h["pod_ip"]] = {"rt": h["runtime"], "start": start, "end": start, "ok": {h["targets"][a][0] for a in allowed}}
        elif l.startswith("A "):
            f = l.split(); t = int(f[1]); pods[h["pod_ip"]]["end"] = t
            if t >= start and f[2] not in allowed: tries[h["runtime"]] += 1
passed = collections.Counter()
for l in op("raw/main/cap/conntrack-events.log.gz"):
    if "[NEW]" not in l: continue
    m = re.search(r"\[(\d+\.\d+)\].*?src=(\S+) dst=(\S+) sport=\d+ dport=(\d+)", l)
    q = pods.get(m.group(2)) if m else None
    if q and q["start"] <= float(m.group(1)) * 1000 <= q["end"] and f"{m.group(3)}:{m.group(4)}" not in q["ok"]: passed[q["rt"]] += 1
print(f"long-running pods ({len(pods)}), after their first 5 s")
for rt in ("kata", "runc"): print(f"  {rt:<5} forbidden tries {tries[rt]:>8,} | let through by the node: {passed[rt]}")
