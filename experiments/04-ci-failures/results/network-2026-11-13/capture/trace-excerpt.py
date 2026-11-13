#!/usr/bin/env python3
"""Capture helper (c24), runs on the Mac in the results folder, over the packet trace recorded on 2026-11-13
(raw/main/cap/trace: xtables-monitor output, one block per traced SYN). It picks the first pod of the start-up batch
that has both a SYN to the metadata endpoint that PASSED and a later one that was REJECTED, and prints the filter-table
lines of one of the two traces. Each printed line is the third field of the trace line as recorded
(table:chain:rule handle:verdict[:target]); lines of chains that are not the policy controller's or flannel's are
left out and counted (with "all" as second argument they are printed too); for the rejecting rule the end of its recorded rule text is printed too. Nothing is rewritten.
usage: python3 capture/trace-excerpt.py passed|rejected [all]"""
import datetime, glob, gzip, json, re, sys
which = sys.argv[1]; everything = len(sys.argv) > 2
def blocks(path):
    blk = []
    for l in gzip.open(path, "rt", errors="replace"):
        if l.startswith("### ") and not l.startswith("### restart"):
            if blk: yield blk
            blk = [l.rstrip("\n")]
        elif l.strip(): blk.append(l.rstrip("\n"))
    if blk: yield blk
MD = "169.254.169.254:80"; passed = {}; rejected = {}
for b in blocks("raw/main/cap/trace/passed-traces.log.gz"):
    f = b[0].split(); fl = [x for x in b if " filter:" in x]
    if f[3] == MD and len(fl) >= 2 and ":ACCEPT" in fl[-1].split()[3] and "FLANNEL-FWD" in fl[-1]: passed.setdefault(f[2].rsplit(":", 1)[0], b)
for b in blocks("raw/main/cap/trace/blocked-samples.log.gz"):
    f = b[0].split(); ip = f[2].rsplit(":", 1)[0]
    if f[3] == MD and ip in passed and int(f[1]) > int(passed[ip][0].split()[1]): rejected.setdefault(ip, b)
heads = {}
for p in sorted(glob.glob("raw/main/batch/b-*.log")):
    if ".init-" not in p: h = json.loads(open(p).readline()[2:]); heads[h["pod_ip"]] = h
both = [i for i in passed if i in rejected]
ip = next((i for i in both if "-kn-" in heads.get(i, {}).get("pod", "")), both[0])      # a Kata pod without the gate if there is one
b = passed[ip] if which == "passed" else rejected[ip]; pod = heads.get(ip, {})
f = b[0].split(); t = datetime.datetime.fromtimestamp(int(f[1]) / 1000, datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
print(f"{t}Z {pod.get('pod', '?')} ({pod.get('runtime', '?')}) {f[2]} -> {f[3]}")
cut = 0; jumps_only = True
for x in (l for l in b if " filter:" in l):
    field = x.split()[3]; chain = field.split(":")[1]
    if not everything and not chain.startswith(("KUBE-ROUTER", "KUBE-POD-FW", "KUBE-NWPLCY", "FLANNEL")) and "KUBE-ROUTER" not in field: cut += 1; jumps_only = jumps_only and ":JUMP:" in field; continue
    print("  " + field[:74])
    if field.endswith(":DROP"): print("      rule text ends: " + re.search(r"-j \S+.*$", x).group(0)[:54])
if cut: print(f"  (+{cut} lines of kube-proxy and Docker chains" + (", jumps only" if jumps_only else "") + ", not shown)")
