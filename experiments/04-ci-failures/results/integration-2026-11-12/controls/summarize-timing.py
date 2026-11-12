#!/usr/bin/env python3
"""Integration (2026-11-12). Summarizes the policy-timing probes (nettime.py logs): for each pod, how long after the
container's process started each target was still reachable. usage: summarize-timing.py <timing-dir>"""
import glob, json, os, re, sys
rows = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "probe-*.log"))):
    txt = open(f).read(); m = re.search(r'NETTIME (\{"event": "summary".*\})', txt)
    name = os.path.basename(f)[6:-4]
    if not m: rows.append((name, None)); continue
    rows.append((name, json.loads(m.group(1))["targets"]))
cols = ["public 1.1.1.1:443", "metadata 169.254.169.254:80", "node ssh", "kubernetes api clusterip", "dns pod tcp 53", "gateway model port", "gateway admin port"]
print("Times are seconds after the container's process started. \"never\" = blocked from the first try; \"always\" = reachable in every try.")
print("Expected once the policy applies: ci-exec nothing; ci-agent only the gateway model port; ci-prep only public 80/443 and DNS.")
print()
print("| Pod | " + " | ".join(c.split(" 1")[0] for c in cols) + " |"); print("|---|" + "---|" * len(cols))
for name, t in rows:
    if t is None: print(f"| {name} | no summary |"); continue
    cell = lambda v: "never" if not v["open"] else ("always" if not v["blocked"] else f"{v['open']} of {v['open'] + v['blocked']} tries; last reachable {v['last_open_s']} s; first blocked {v['first_blocked_s']} s")
    print(f"| {name} | " + " | ".join(cell(t[c]) if c in t else "-" for c in cols) + " |")
