#!/usr/bin/env python3
"""2026-11-13. Two follow-ups on the host-side trace of the main block (xtables-monitor summaries, which carry a time).
1. SYNs to TCP port 4460 from pod addresses. No probe uses that port: they come from the Kata guest itself (4460 is
   the NTS key-exchange port of time servers). When were they sent relative to the pod's first blocked try, and what
   did the filter table do with them?
2. Every SYN the nft trace reported as accepted that nft-verdicts.py could not match to an allowed or start-up try.
usage: extra-checks.py <data-dir>"""
import glob, gzip, json, os, re, sys
D = sys.argv[1]
zo = lambda p: gzip.open(p + ".gz", "rt", errors="replace") if os.path.exists(p + ".gz") else open(p, errors="replace")
t3 = {}      # T3 pods have no policy until it is applied: their reference time is the end of `kubectl apply`, not the first blocked try
for f in (f"{D}/t3-steady-apply.jsonl", f"{D}/t3lat/apply-times.jsonl"):
    if os.path.exists(f):
        for l in open(f):
            r = json.loads(l)
            for p in r.get("pods", "").split(): t3[p] = r["apply_end_ms"]
lopen = lambda p: gzip.open(p, "rt", errors="replace") if p.endswith(".gz") else open(p, errors="replace")   # probe logs may be stored compressed
logs = lambda pat: sorted(glob.glob(pat) + glob.glob(pat + ".gz"))
base = lambda p: p[:-7] if p.endswith(".gz") else p[:-4]
pods = []
for p in sorted(logs(f"{D}/steady*/*.log") + logs(f"{D}/batch/*.log") + logs(f"{D}/t3lat/t3lat-*.log")):
    if ".init-" in p: continue
    h = None; fb = None; last = None; we = None
    for l in lopen(p):
        if l.startswith("H "): h = json.loads(l[2:]); allowed = set(h.get("allowed", []))
        elif l.startswith("A ") and h:
            f = l.split(); last = int(f[1])
            if fb is None and f[2] not in allowed and (f[3] != "o" or (len(f) > 6 and f[6] != "st=1")): fb = int(f[1])
            if f[2] not in allowed and f[3] == "o" and (len(f) < 7 or f[6] == "st=1") and int(f[1]) - h["t0_epoch_ms"] < 5000: we = int(f[1])   # end of the start-up window
    if h: pods.append({"pod": h["pod"], "ip": h["pod_ip"], "rt": h["runtime"], "t0": h["t0_epoch_ms"], "first_block": t3.get(h["pod"], fb), "window_end": we, "end": last, "t3": h["pod"] in t3})
gate = {}
for p in glob.glob(f"{D}/batch/*.pod.json"):
    j = json.load(open(p)); gate[j["plan"]["name"]] = j["plan"].get("gate")
def owner(ip, t):
    c = [q for q in pods if q["ip"] == ip and q["t0"] - 60000 <= t <= (q["end"] or q["t0"]) + 5000]
    return min(c, key=lambda q: abs(q["t0"] - t)) if c else None
complete = set(); key = None; lastf = ""; nf = 0
def close(key, lastf, nf):   # passed = the LAST filter-table line of the trace is a final accept
    if key and re.search(r" filter:(FLANNEL-FWD|KUBE-NWPLCY-TAIL|KUBE-FORWARD):rule:0x[0-9a-f]+:ACCEPT| filter:INPUT:policy:ACCEPT", lastf) and (nf >= 2 or "policy" not in lastf): complete.add(key)   # a policy line alone is the stray first line
for l in zo(f"{D}/cap/trace/passed-traces.log"):
    if l.startswith("### ") and not l.startswith("### restart"): close(key, lastf, nf); f = l.split(); key = (f[1], f[2]); lastf = ""; nf = 0
    elif " filter:" in l: lastf = l; nf += 1
close(key, lastf, nf)
rows = []
for l in zo(f"{D}/cap/trace/packets.log"):
    f = l.split()
    if len(f) >= 8 and f[3].endswith(":4460"):
        v = "blocked" if f[5] == "blocked" else ("passed" if (f[1], f[2]) in complete else "incomplete trace")
        rows.append((int(f[1]), f[2].rsplit(":", 1)[0], v))
print(f"1. SYNs to port 4460 from pod addresses in the trace summaries: {len(rows)}; by verdict: " + str({v: sum(1 for r in rows if r[2] == v) for v in ('blocked', 'passed', 'incomplete trace')}))
tally = {}; late_pass = []
for t, ip, v in rows:
    q = owner(ip, t)
    if not q: k = ("address of no probe pod at that time", v)
    else:
        when = "before the container's process started" if t < q["t0"] else "inside the pod's start-up window (before its last established forbidden connection, +0.3 s)" if q["window_end"] and t <= q["window_end"] + 300 else ("before the pod's first blocked try (T3 pods: before the policy was applied)" if q["first_block"] and t < q["first_block"] else "after the pod's first blocked try (T3 pods: after the policy was applied)")
        k = (f"{q['rt']} pod, {when}", v)
        if v == "passed" and when.startswith("after"): late_pass.append((t, ip, q["pod"], t - q["first_block"]))
    tally[k] = tally.get(k, 0) + 1
for k, n in sorted(tally.items()): print(f"   - {k[0]}: {k[1]}: {n}")
for x in late_pass: print("   passed after the reference time:", x)
print("   source addresses by runtime of the owning probe pod:", {rt: len({ip for t, ip, v in rows if (owner(ip, t) or {}).get('rt') == rt}) for rt in ("kata", "runc")}, "pods")
# Version 2 (review follow-up): the accepted SYNs are classified by nft-verdicts.py version 2 (address, port, destination and
# time); every unexplained or ambiguous one is in nft-verdicts-examined.jsonl. Version 1 of this part is in extra-checks-v1.py.
s = json.load(open(f"{D}/nft-verdicts-summary.json"))
print("2. accepted SYNs in the nft trace by class (nft-verdicts.py version 2):")
for k, v in sorted(s["accepted_by_class"].items()): print(f"   - {k}: {v}")
print(f"   unexplained or ambiguous, examined one by one: {s['examined']}")
ex = f"{D}/nft-verdicts-examined.jsonl"
if os.path.exists(ex):
    for l in open(ex): j = json.loads(l); print("   -", j["src"], j["sport"], "->", j["dst"] or j["dst_after_translation"], "|", j["class"], "| SYN-ACK in pcap:", j.get("pcap_synack_to_the_pod"))
