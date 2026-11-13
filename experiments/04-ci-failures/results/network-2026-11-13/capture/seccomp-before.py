#!/usr/bin/env python3
"""Capture helper (c23b), runs on the Mac in the results folder: reads the first line of every saved probe log (the
probe prints /proc/self/status fields of its own process there) and counts the pods by runtime and Seccomp value,
before and after the Kata drop-in was installed. Counts only; nothing else is read.  usage: python3 capture/seccomp-before.py"""
import collections, glob, gzip, json
def heads(dirs):
    c = collections.Counter()
    for d in dirs:
        for p in sorted(glob.glob(d + "/*.log") + glob.glob(d + "/*.log.gz")):
            if ".init-" in p or "driver" in p: continue
            l = (gzip.open(p, "rt") if p.endswith(".gz") else open(p)).readline()
            if not l.startswith("H "): continue
            h = json.loads(l[2:]); c[(h.get("runtime", "?"), h["status"].get("Seccomp"), h["status"].get("Seccomp_filters"))] += 1
    return c
def show(title, c):
    print(title)
    for rt in ("kata", "runc"):
        n = sum(v for k, v in c.items() if k[0] == rt)
        if n: print(f"  {rt:<5}{n:4d} pods | " + " | ".join(f"Seccomp: {k[1]}, filters: {k[2]} in {v}" for k, v in sorted(c.items()) if k[0] == rt))
show("first session, default Kata configuration (08:45 to 09:25Z):", heads(["raw/pilot", "raw/main/steady", "raw/main/steady2", "raw/main/batch", "raw/main/t3lat", "raw/race/pods"]))
show("after the drop-in (helm upgrade 09:25Z; reinstall 12:00Z):", heads(["raw/t5/pods", "raw/t4tuned/pods", "review-followup/c/pods"]))
