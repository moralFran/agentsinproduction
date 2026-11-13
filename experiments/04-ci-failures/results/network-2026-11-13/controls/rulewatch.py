#!/usr/bin/env python3
"""2026-11-13, runs ON the VM as root. Timestamped snapshots of the rule set the policy controller writes: the filter
table (iptables-save, counters and comments removed) and the ipsets (ipset save, members sorted). The first snapshot of
each is written in full; afterwards only a unified diff whenever the text changed, with the epoch-ms time just before
and just after the command that read it. usage: rulewatch.py <out-dir> [interval_s]"""
import difflib, os, re, subprocess, sys, time
out = sys.argv[1]; interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5; os.makedirs(out, exist_ok=True)
def filt():
    t = subprocess.run(["iptables-save", "-t", "filter"], capture_output=True, text=True).stdout
    return [re.sub(r"^(:\S+ \S+) \[\d+:\d+\]", r"\1", l) for l in t.splitlines() if not l.startswith("#")]
def sets():
    t = subprocess.run(["ipset", "save"], capture_output=True, text=True).stdout.splitlines()
    return sorted(l for l in t if l.startswith("create")) + sorted(l for l in t if l.startswith("add"))
src = {"filter": filt, "ipset": sets}; prev = {}; logs = {k: open(f"{out}/{k}-changes.log", "a", buffering=1) for k in src}
while True:
    for k, f in src.items():
        a = int(time.time() * 1000); cur = f(); b = int(time.time() * 1000)
        if k not in prev:
            open(f"{out}/{k}-first-{a}.txt", "w").write("\n".join(cur) + "\n"); logs[k].write(f"=== {a} {b} first snapshot, {len(cur)} lines\n")
        elif cur != prev[k]:
            d = [l for l in difflib.unified_diff(prev[k], cur, n=0, lineterm="") if not l.startswith(("---", "+++", "@@"))]
            logs[k].write(f"=== {a} {b} changed, {len(cur)} lines\n" + "\n".join(d) + "\n")
        prev[k] = cur
    time.sleep(interval)
