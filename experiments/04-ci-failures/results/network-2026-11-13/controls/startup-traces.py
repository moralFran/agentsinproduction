#!/usr/bin/env python3
"""2026-11-13 (saved in the review follow-up; the count in the first report came from the same code run by hand).
Complete traces of SYNs that PASSED to the metadata endpoint or the node's ssh port from pods whose namespace had its
policy from the start (the T3 pods are left out): does the trace contain a jump for the packet's own source address
into a KUBE-POD-FW-* chain? A trace is complete when its LAST filter-table line is the final accept (and, for the
INPUT policy, at least one rule line precedes it). No join with the probe logs is involved.
usage: startup-traces.py <data-dir> [example-out.txt]"""
import collections, glob, gzip, json, os, re, sys
D = sys.argv[1]
zo = lambda p: gzip.open(p + ".gz", "rt", errors="replace") if os.path.exists(p + ".gz") else open(p, errors="replace")
lopen = lambda p: gzip.open(p, "rt", errors="replace") if p.endswith(".gz") else open(p, errors="replace")   # probe logs may be stored compressed
logs = lambda pat: sorted(glob.glob(pat) + glob.glob(pat + ".gz"))
base = lambda p: p[:-7] if p.endswith(".gz") else p[:-4]
t3ips = {json.loads(lopen(p).readline()[2:])["pod_ip"] for p in logs(f"{D}/steady/steady-t3-*.log") + logs(f"{D}/t3lat/t3lat-*.log")}
node = next(json.loads(lopen(p).readline()[2:])["targets"]["node22"][0] for p in logs(f"{D}/steady/*.log"))
c = collections.Counter(); ex = None; blk = []
def done():
    global ex
    if not blk: return
    f = blk[0].split(); src = f[2].rsplit(":", 1)[0]
    if f[3] not in ("169.254.169.254:80", node) or src in t3ips: return
    fl = [x for x in blk if " filter:" in x]
    if len(fl) < 2 or not re.search(r" filter:(FLANNEL-FWD|KUBE-NWPLCY-TAIL|KUBE-FORWARD):rule:0x[0-9a-f]+:ACCEPT| filter:INPUT:policy:ACCEPT", fl[-1]): return
    own = re.search(r"-s %s/32 [^\n]*-j KUBE-POD-FW" % re.escape(src), "".join(blk)) is not None
    c[(f[3], "a jump for this source address is present" if own else "no jump for this source address")] += 1
    if not own and ex is None and f[3].startswith("169"): ex = "".join(x[:200] + "\n" for x in blk if x.strip())
for l in zo(f"{D}/cap/trace/passed-traces.log"):
    if l.startswith("### ") and not l.startswith("### restart"): done(); blk = [l]
    else: blk.append(l)
done()
for k, v in sorted(c.items()): print(f"{k[0]}: {k[1]}: {v}")
print("total complete passed traces:", sum(c.values()), "| without a jump for the source address:", sum(v for k, v in c.items() if k[1].startswith("no jump")))
if len(sys.argv) > 2 and ex: open(sys.argv[2], "w").write("# One SYN that passed during a pod's first moments (from raw/main/cap/trace/passed-traces.log.gz): metadata endpoint, forwarded.\n# No KUBE-POD-FW chain is entered for the source address; the packet is accepted by flannel's forward rule.\n" + ex)
