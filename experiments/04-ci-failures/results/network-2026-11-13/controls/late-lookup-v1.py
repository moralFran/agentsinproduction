#!/usr/bin/env python3
"""2026-11-13, runs ON the VM. For every try in the probe logs where connect() returned without an error on a FORBIDDEN
target AFTER that target had already been blocked in the same pod ("late"), collects what the host saw of that exact
SYN (pod address + source port):
  trace      the summary line(s) of the packet trace (blocked / passed, deciding chain)
  conntrack  NEW events for that source address and port (a connection the firewall let through creates one)
  pcap       the packets on cni0 with that address and port (SYN, SYN-ACK, RST) and ICMP errors quoting it
             (the capture started at 08:59Z; earlier events have none)
Also lists, for comparison, up to 40 start-up connections (before the first block) with the same evidence.
usage: late-lookup.py <cap-dir> <t3-apply.jsonl or -> <out.jsonl> <log-dir>..."""
import glob, json, os, re, subprocess, sys
cap, t3f, out = sys.argv[1], sys.argv[2], sys.argv[3]; dirs = sys.argv[4:]
t3 = {}
if t3f != "-" and os.path.exists(t3f):
    for l in open(t3f):
        r = json.loads(l)
        for p in r.get("pods", "").split(): t3[p] = r["apply_end_ms"] + 5000
for d in dirs:
    f = os.path.join(d, "apply-times.jsonl")
    if os.path.exists(f):
        for l in open(f):
            r = json.loads(l)
            for p in r.get("pods", "").split(): t3[p] = r["apply_end_ms"] + 5000
events = []
for d in dirs:
    for p in sorted(glob.glob(os.path.join(d, "*.log"))):
        if ".init-" in p or "driver" in p: continue
        h = None; blocked = {}; n_start = 0
        for l in open(p, errors="replace"):
            if l.startswith("H "): h = json.loads(l[2:]); allowed = set(h.get("allowed", [])); pf = t3.get(h["pod"], 0); continue
            if not l.startswith("A ") or not h: continue
            f = l.split()
            if len(f) < 6 or f[2] in allowed or int(f[1]) < pf: continue
            if f[3] != "o": blocked.setdefault(f[2], int(f[1])); continue
            kind = "late" if f[2] in blocked else "startup"
            if kind == "startup":
                n_start += 1
                if n_start > 2: continue
            events.append({"kind": kind, "t_ms": int(f[1]), "pod": h["pod"], "role": h["role"], "runtime": h["runtime"], "pod_ip": h["pod_ip"], "target": f[2],
                           "addr": h["targets"][f[2]][0], "class": h["targets"][f[2]][1], "sport": int(f[5]), "dur_ms": int(f[4]), "rel_s": round((int(f[1]) - h["t0_epoch_ms"]) / 1000, 2),
                           "socket": " ".join(f[6:]) or "not recorded (probe v1)"})
startups = [e for e in events if e["kind"] == "startup"]; events = [e for e in events if e["kind"] == "late"] + startups[:: max(1, len(startups) // 40)][:40]
want = {f"{e['pod_ip']}:{e['sport']}" for e in events}; tr = {}; ctk = {}
for l in open(f"{cap}/trace/packets.log", errors="replace"):
    f = l.split()
    if len(f) >= 8 and f[2] in want: tr.setdefault(f[2], []).append(" ".join(f[1:]))
for l in open(f"{cap}/conntrack-events.log", errors="replace"):
    m = re.search(r"src=(\S+) dst=\S+ sport=(\d+) ", l)
    if m and f"{m.group(1)}:{m.group(2)}" in want and "[NEW]" in l: ctk.setdefault(f"{m.group(1)}:{m.group(2)}", []).append(" ".join(l.split()))
pcap = f"{cap}/cni0-syn-rst-icmp.pcap"
with open(out, "w") as o:
    for e in events:
        k = f"{e['pod_ip']}:{e['sport']}"   # source ports repeat over time: keep what the host saw within 3 s of the try
        e["trace"] = [x for x in tr.get(k, []) if abs(int(x.split()[0]) - e["t_ms"]) < 3000]
        e["conntrack_new"] = [x for x in ctk.get(k, []) if abs(float(x.split("]")[0].strip("[")) * 1000 - e["t_ms"]) < 3000]
        if os.path.exists(pcap):
            r = subprocess.run(["tcpdump", "-r", pcap, "-n", "-tt", "-v", f"host {e['pod_ip']} and ((tcp port {e['sport']}) or icmp)"], capture_output=True, text=True).stdout
            lines = [" ".join(x.split()) for x in re.sub(r"\n[ \t]+", " ", r).splitlines() if f".{e['sport']} " in x or f".{e['sport']}:" in x]
            def ts(x):
                try: return float(x.split()[0]) * 1000
                except ValueError: return 0
            near = [x for x in lines if abs(ts(x) - e["t_ms"]) < 3000]
            e["pcap"] = [x[:260] for x in near][:8]; e["pcap_synack"] = sum(1 for x in near if "Flags [S.]" in x); e["pcap_icmp_unreachable"] = sum(1 for x in near if "unreachable" in x)
        o.write(json.dumps(e) + "\n")
late = [e for e in events if e["kind"] == "late"]
# Fallback for late tries the xtables-monitor reader missed (it restarted often under load): the same packets in the
# nft monitor trace, which did not restart. No timestamps there: matched by source address, source port and destination.
nftf = f"{cap}/trace/raw-nft-trace.log"; missing = [e for e in late if not e["trace"]]
if missing and os.path.exists(nftf):
    ports = "|".join(sorted({str(e["sport"]) for e in missing}))
    p1 = subprocess.run(["grep", "-a", "-E", f"tcp sport ({ports}) ", nftf], capture_output=True, text=True, errors="replace").stdout.splitlines()
    ids = {}
    for l in p1:
        m = re.search(r"trace id (\S+) .*ip saddr (\S+) ip daddr (\S+) .*tcp sport (\d+) tcp dport (\d+)", l)
        if not m: continue
        for e in missing:
            host, port = e["addr"].rsplit(":", 1)
            if m.group(2) == e["pod_ip"] and int(m.group(4)) == e["sport"] and (m.group(3) == host or " nat PREROUTING " not in l and " raw PREROUTING " not in l):
                ids.setdefault(m.group(1), []).append(e)
    if ids:
        open("/tmp/nft-ids.txt", "w").write("\n".join(f"trace id {i} " for i in ids) + "\n")
        p2 = subprocess.run(["grep", "-a", "-F", "-f", "/tmp/nft-ids.txt", nftf], capture_output=True, text=True, errors="replace").stdout.splitlines()
        for l in p2:
            i = l.split()[2]
            if "verdict" in l and " packet: " not in l:
                for e in ids.get(i, []): e.setdefault("nft_trace", []).append(" ".join(l.split()[3:])[:200])
    for e in missing:
        v = e.get("nft_trace", []); e["nft_verdict"] = "blocked" if any("verdict drop" in x for x in v) else ("passed" if v else "no nft trace found")
    with open(out, "w") as o:
        for e in events: o.write(json.dumps(e) + "\n")
    print("  late tries without an xtables-monitor line:", len(missing), "| in the nft trace: blocked", sum(1 for e in missing if e["nft_verdict"] == "blocked"), "passed", sum(1 for e in missing if e["nft_verdict"] == "passed"), "not found", sum(1 for e in missing if e["nft_verdict"].startswith("no")))
print(f"late connections: {len(late)}; by runtime: " + str({rt: sum(1 for e in late if e['runtime'] == rt) for rt in ('kata', 'runc')}))
print("  with a trace line:", sum(1 for e in late if e["trace"]), "| trace says blocked:", sum(1 for e in late if e["trace"] and all(" blocked " in x for x in e["trace"])), "| trace says passed:", sum(1 for e in late if any(" passed " in x for x in e["trace"])))
print("  with a conntrack NEW event:", sum(1 for e in late if e["conntrack_new"]))
print("  with packets in the pcap:", sum(1 for e in late if e.get("pcap")), "| SYN-ACK seen:", sum(1 for e in late if e.get("pcap_synack")), "| ICMP unreachable seen:", sum(1 for e in late if e.get("pcap_icmp_unreachable")))
print("  socket state after connect():", {s: sum(1 for e in late if e["socket"] == s) for s in sorted({e["socket"] for e in late})})
su = [e for e in events if e["kind"] == "startup"]
print(f"start-up connections sampled: {len(su)}; trace passed: {sum(1 for e in su if any(' passed ' in x for x in e['trace']))}; conntrack NEW: {sum(1 for e in su if e['conntrack_new'])}; SYN-ACK in pcap: {sum(1 for e in su if e.get('pcap_synack'))}; socket: " + str({s: sum(1 for e in su if e['socket'] == s) for s in sorted({e['socket'] for e in su})}))
