#!/usr/bin/env python3
"""2026-11-13, runs ON the VM. Host-side check that does not depend on what connect() returned in the pods and not on
xtables-monitor (which restarted about two thousand times under load and printed stale rule text while the table was
being replaced): the raw `nft monitor trace` of every TCP SYN from a pod address. For each packet the filter-table
verdict the kernel reported: drop (the REJECT rules) or accept. Then every ACCEPTED SYN is looked up in the probe logs
by pod address and source port:
  allowed       the try went to a destination the pod's policy allows
  start-up      the try is one the probe logged as connected BEFORE that target was first blocked in the pod (the window)
  pre-policy    T3 pods: before the policy was applied (+5 s)
  UNEXPLAINED   the host accepted a SYN to a forbidden destination outside the window -> a real late leak
usage: nft-verdicts.py <raw-nft-trace.log> <out-prefix> <t3-apply.jsonl or -> <log-dir>..."""
import glob, json, os, re, sys
raw, outp, t3f = sys.argv[1], sys.argv[2], sys.argv[3]; dirs = sys.argv[4:]
key = {}; verdict = {}; order = []
pk = re.compile(r"ip saddr (\S+) ip daddr (\S+) .*ip id (\d+) .*tcp sport (\d+) tcp dport (\d+)")
# Seen in the raw trace: for some packets the filter-table trace starts with a line "FORWARD policy accept" (or INPUT),
# then the packet line is printed AGAIN and the normal rule lines follow, ending in the drop. The FORWARD chain's policy
# on this node is DROP, so that first line is not the chain's verdict. Both parts are one packet (same addresses, ports
# and IP id): they are merged here and a drop anywhere wins. The number of packets with such a line is reported.
# "chain policy accept" below = the trace has a policy-accept line and no rule that accepted or dropped: the normal trace
# of a SYN to the node itself (INPUT, policy ACCEPT) when no pod chain matched it, or a trace whose later lines were lost.
early_policy = 0
n = 0
with open(raw, errors="replace") as f:
    for l in f:
        if not l.startswith("trace id ") or " ip filter " not in l: continue
        i = l[9:17]
        if " packet: " in l:
            m = pk.search(l)
            if m:
                k = (m.group(1), int(m.group(4)), f"{m.group(2)}:{m.group(5)}", int(m.group(3))); key[i] = k
                if k not in verdict: verdict[k] = "no verdict line"; n += 1
        elif i in key:
            k = key[i]
            if "verdict drop" in l: verdict[k] = "drop"
            elif "policy accept" in l and verdict[k] == "no verdict line": verdict[k] = "chain policy accept"; early_policy += 1
            elif "verdict accept" in l and verdict[k] != "drop": verdict[k] = "accept"
tot = {}
for (src, sp, dst, _), v in verdict.items(): tot[v] = tot.get(v, 0) + 1
print("SYNs from pod addresses seen at the filter table:", len(verdict), tot, "| packets whose first filter line was a policy-accept line:", early_policy)
t3 = {}
for fpath in [t3f] + [os.path.join(d, "apply-times.jsonl") for d in dirs]:
    if fpath != "-" and os.path.exists(fpath):
        for l in open(fpath):
            r = json.loads(l)
            for p in r.get("pods", "").split(): t3[p] = r["apply_end_ms"] + 5000
tries = {}      # (pod ip, sport) -> list of (pod, label, class)
for d in dirs:
    for p in sorted(glob.glob(os.path.join(d, "*.log"))):
        if ".init-" in p or "driver" in p: continue
        h = None; blocked = set()
        for l in open(p, errors="replace"):
            if l.startswith("H "): h = json.loads(l[2:]); allowed = set(h.get("allowed", [])); pf = t3.get(h["pod"], 0); continue
            if not l.startswith("A ") or not h: continue
            f = l.split()
            if len(f) < 6: continue
            if f[2] in allowed: c = "allowed"
            elif int(f[1]) < pf: c = "pre-policy"
            elif f[3] == "o" and f[2] not in blocked and (len(f) < 7 or f[6] == "st=1"): c = "start-up"
            else:
                c = "blocked-or-late:" + f[3] + ("" if len(f) < 7 else "," + f[6]); blocked.add(f[2])
            tries.setdefault((h["pod_ip"], int(f[5])), []).append((h["pod"], f[2], c))
probe_ips = {ip for ip, _ in tries}; cls = {}; unexplained = []
with open(outp + "-accepted.txt", "w") as o:
    for (src, sp, dst, _), v in verdict.items():
        if v not in ("accept", "chain policy accept") or src not in probe_ips: continue
        t = tries.get((src, sp), [])
        kinds = {c.split(":")[0] for _, _, c in t}
        c = "allowed" if "allowed" in kinds else "start-up" if "start-up" in kinds else "pre-policy" if "pre-policy" in kinds else "no probe try with this port" if not t else "UNEXPLAINED"
        c = c + (" (rule accept)" if v == "accept" else " (chain policy accept, no accepting or dropping rule)")
        cls[c] = cls.get(c, 0) + 1; o.write(f"{src}:{sp} -> {dst} {c} {t[:3]}\n")
        if c.startswith(("UNEXPLAINED", "no probe try with this port")): unexplained.append((src, sp, dst, c, t[:3]))
print("accepted SYNs from probe pod addresses, by explanation:", cls)
for u in unexplained[:40]: print("  ", u)
nov = [(k, v) for k, v in verdict.items() if v == "no verdict line" and k[0] in probe_ips]
print("SYNs from probe pod addresses with no verdict line in the trace (trace events lost):", len(nov))
json.dump({"filter_table_syns": len(verdict), "verdicts": tot, "accepted_from_probe_pods": cls, "unexplained": [list(u[:4]) for u in unexplained], "no_verdict_from_probe_pods": len(nov)}, open(outp + "-summary.json", "w"), indent=1)
