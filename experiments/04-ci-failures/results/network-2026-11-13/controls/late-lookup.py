#!/usr/bin/env python3
"""2026-11-13, runs ON the VM. For every try in the probe logs where connect() returned without an error on a FORBIDDEN
target AFTER that target had already been blocked in the same pod ("late"), collects what the host saw of that exact
SYN (pod address + source port):
  trace      the summary line(s) of the packet trace (blocked / passed, deciding chain)
  conntrack  NEW events for that source address and port (a connection the firewall let through creates one)
  pcap       the packets on cni0 with that address and port (SYN, SYN-ACK, RST) and ICMP errors quoting it
             (the capture started at 08:59Z; earlier events have none)
Version 2 (review follow-up; version 1 is late-lookup-v1.py): the trace line, the conntrack event and the nft trace must
have the try's DESTINATION as well as its source address and port (version 1 took any line with that address and port
within 3 s, so a line of another try that reused the port could stand in). The pcap count stays deliberately wide: ANY
SYN-ACK sent to that pod address and port within 3 s counts.
Version 3: see the block "Version 3" below (per-packet verdicts; status per event).
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
    m = re.search(r"src=(\S+) dst=(\S+) sport=(\d+) dport=(\d+) ", l)
    if m and f"{m.group(1)}:{m.group(3)}" in want and "[NEW]" in l: ctk.setdefault(f"{m.group(1)}:{m.group(3)}", []).append((f"{m.group(2)}:{m.group(4)}", " ".join(l.split())))
pcap = f"{cap}/cni0-syn-rst-icmp.pcap"
with open(out, "w") as o:
    for e in events:
        k = f"{e['pod_ip']}:{e['sport']}"   # source ports repeat over time: keep what the host saw within 3 s of the try
        e["trace"] = [x for x in tr.get(k, []) if abs(int(x.split()[0]) - e["t_ms"]) < 3000 and x.split()[2] == e["addr"]]
        e["trace_other_destination_same_port"] = [x for x in tr.get(k, []) if abs(int(x.split()[0]) - e["t_ms"]) < 3000 and x.split()[2] != e["addr"]]
        e["conntrack_new"] = [x for d, x in ctk.get(k, []) if d == e["addr"] and abs(float(x.split("]")[0].strip("[")) * 1000 - e["t_ms"]) < 3000]
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
# ---- Version 3 (second review correction; version 2 is late-lookup-v2.py). Version 2 pooled the filter-table verdict
# lines of ALL packets in the nft trace with the event's address, port and destination and called the event blocked if
# any of them was a drop: an old rejected packet could hide a later accepted one. Version 3 works per PACKET.
#  packets: every packet in the nft trace with the event's key (own PREROUTING line = destination before translation,
#           IP id), in file order (chronological), each with its OWN filter verdict (drop / accept / policy accept / none);
#           verdict lines are tied to a packet by trace id AND position in the file (trace ids repeat over time);
#  tries:   every probe try of that pod with the same source port and target, with time and class;
#  status:  see status() below; an event is "blocked" only by a time-matched line, by a key whose packets were ALL
#           dropped (at least as many packets as tries), or after another timed source separated the packets; else
#           "inconclusive". An accepted packet that the timed sources put at the event is reported as ACCEPTED.
nftf = f"{cap}/trace/raw-nft-trace.log"
want_pairs = {(e["pod_ip"], e["sport"]) for e in late}
tries_k = {}
for d in dirs:
    for p in sorted(glob.glob(os.path.join(d, "*.log"))):
        if ".init-" in p or "driver" in p: continue
        h = None; blocked = set()
        for l in open(p, errors="replace"):
            if l.startswith("H "): h = json.loads(l[2:]); allowed = set(h.get("allowed", [])); pf = t3.get(h["pod"], 0); continue
            if not l.startswith("A ") or not h: continue
            f = l.split()
            if len(f) < 6: continue
            est = f[3] == "o" and (len(f) < 7 or f[6] == "st=1")
            c = "allowed" if f[2] in allowed else "pre-policy" if int(f[1]) < pf else "start-up" if est and f[2] not in blocked else "late: connect() returned no error" if f[3] == "o" else "blocked in the probe"
            if c in ("late: connect() returned no error", "blocked in the probe"): blocked.add(f[2])
            if (h["pod_ip"], int(f[5])) in want_pairs: tries_k.setdefault((h["pod_ip"], int(f[5]), h["targets"][f[2]][0]), []).append({"t": int(f[1]), "class": c, "result": " ".join(f[3:5] + f[6:])})
pkts = {}
if os.path.exists(nftf) and late:
    ports = "|".join(sorted({str(e["sport"]) for e in late}))
    p1 = subprocess.run(["grep", "-a", "-n", "-E", f"tcp sport ({ports}) ", nftf], capture_output=True, text=True, errors="replace").stdout.splitlines()
    pat = re.compile(r"^(\d+):trace id (\S+) .*ip saddr (\S+) ip daddr (\S+) .*ip id (\d+) .*tcp sport (\d+) tcp dport (\d+)")
    byid = {}
    for l in p1:
        m = pat.search(l)
        if not m or (m.group(3), int(m.group(6))) not in want_pairs: continue
        k = (m.group(3), int(m.group(6)), m.group(5)); P = pkts.setdefault(k, {"seq": int(m.group(1)), "pre": None, "ip_id": int(m.group(5)), "v": "no filter verdict line", "filter_lines": []})
        if " ip raw PREROUTING " in l and P["pre"] is None: P["pre"] = f"{m.group(4)}:{m.group(7)}"
        if " ip filter " in l: byid.setdefault(m.group(2), []).append((int(m.group(1)), k)); P["filter_lines"].append(int(m.group(1)))
    if byid:
        open("/tmp/nft-ids.txt", "w").write("\n".join(f"trace id {i} " for i in byid) + "\n")
        p2 = subprocess.run(["grep", "-a", "-n", "-F", "-f", "/tmp/nft-ids.txt", nftf], capture_output=True, text=True, errors="replace").stdout.splitlines()
        cur = {}
        for l in p2:
            n, _, rest = l.partition(":"); n = int(n); f = rest.split(); i = f[2] if len(f) > 2 else ""
            if " packet: " in rest:      # a packet line with this trace id: ours (then it opens the packet) or another packet reusing the id (then it closes ours)
                cur[i] = next((k for ln, k in byid.get(i, []) if ln == n), None); continue
            k = cur.get(i)
            if k is None or " ip filter " not in rest or n - pkts[k]["filter_lines"][0] > 5000: continue
            P = pkts[k]
            if "verdict drop" in rest: P["v"] = "drop"
            elif "verdict accept" in rest and P["v"] != "drop": P["v"] = "accept"
            elif "policy accept" in rest and P["v"] == "no filter verdict line": P["v"] = "policy accept"
ct_all = {}
for l in open(f"{cap}/conntrack-events.log", errors="replace"):
    m = re.search(r"\[(\d+\.\d+)\].*?\[NEW\].*?src=(\S+) dst=(\S+) sport=(\d+) dport=(\d+) ", l)
    if m and (m.group(2), int(m.group(4))) in want_pairs: ct_all.setdefault((m.group(2), int(m.group(4)), f"{m.group(3)}:{m.group(5)}"), []).append(float(m.group(1)) * 1000)
def status(e):
    k = (e["pod_ip"], e["sport"], e["addr"]); host = e["addr"].rsplit(":", 1)[0]
    P = sorted((p for kk, p in pkts.items() if kk[0] == e["pod_ip"] and kk[1] == e["sport"] and p["pre"] == e["addr"]), key=lambda p: p["seq"])
    T = sorted(tries_k.get(k, []), key=lambda t: t["t"]); cts = ct_all.get(k, [])
    e["packets_with_this_key"] = [{"ip_id": p["ip_id"], "line": p["seq"], "verdict": p["v"]} for p in P]; e["tries_with_this_key"] = T; e["conntrack_new_times_for_this_key"] = cts
    others = [t for t in T if t["t"] != e["t_ms"] and abs(t["t"] - e["t_ms"]) < 3000]; e["other_tries_same_key_within_3s"] = len(others)
    acc = [p for p in P if p["v"] in ("accept", "policy accept")]; drop = [p for p in P if p["v"] == "drop"]
    if e["conntrack_new"]: return "ACCEPTED", "a conntrack NEW event for this address, port and destination within 3 s of the try"
    if e["trace"] and not others:
        return ("blocked", "time-matched xtables-monitor line (same address, port, destination, within 3 s; no other try with this key within 3 s)") if all(" blocked " in x for x in e["trace"]) else ("ACCEPTED", "time-matched xtables-monitor line says passed")
    if not P: return "no trace", "no packet with this key in the nft trace and no time-matched xtables-monitor line"
    if len(T) == 1 and len(P) == 1: return ("blocked", "one try and one packet with this key; that packet was dropped") if drop else (("ACCEPTED", "one try and one packet with this key; that packet was accepted") if acc else ("inconclusive", "the only packet of this key has no filter verdict line"))
    if len(drop) == len(P) and len(P) >= len(T): return "blocked", f"every packet of this key was dropped ({len(P)} packets, {len(T)} tries)"
    pc = [x for x in e.get("pcap", []) if host in x]
    if acc and len(cts) >= len(acc) and drop: return "blocked", f"separated by conntrack: the {len(acc)} accepted packet(s) of this key have NEW events at {[round((c - e['t_ms']) / 1000, 1) for c in cts]} s from this try, none within 3 s; {len(drop)} packet(s) of the key were dropped ({len(P)} packets, {len(T)} tries)"
    if pc and not e.get("pcap_synack") and any("unreachable" in x for x in pc): return "blocked", "separated by the pcap: within 3 s of the try a SYN to this destination is answered by ICMP port-unreachable and there is no SYN-ACK"
    if len(P) == len(T):
        v = P[[t["t"] for t in T].index(e["t_ms"])]["v"] if e["t_ms"] in [t["t"] for t in T] else None
        if v == "drop": return "blocked", f"separated by order: the tries and the packets of this key are equal in number ({len(T)}); this try's packet, by position, was dropped"
        if v in ("accept", "policy accept"): return "ACCEPTED", f"by order: the tries and the packets of this key are equal in number ({len(T)}); this try's packet, by position, was accepted"
    return "inconclusive", f"{len(P)} packets ({len(drop)} dropped, {len(acc)} accepted) for {len(T)} tries with this key; no timed source separates them"
for e in late: e["status"], e["status_why"] = status(e)
with open(out, "w") as o:
    for e in events: o.write(json.dumps(e) + "\n")
tally = {}
for e in late:
    w = e["status_why"]; w = re.sub(r"\(\d+ packets, \d+ tries\)|\(\d+\)|the \d+ accepted.*", "", w).strip()
    tally[(e["status"], w[:110])] = tally.get((e["status"], w[:110]), 0) + 1
print("late events by status (version 3, per packet):")
for (st, w), n in sorted(tally.items()): print(f"  {n:4d}  {st}: {w}")
print("  events whose key (address, port, destination) had more than one try:", sum(1 for e in late if len(e["tries_with_this_key"]) > 1), "| more than one packet:", sum(1 for e in late if len(e["packets_with_this_key"]) > 1), "| another try with the key within 3 s:", sum(1 for e in late if e["other_tries_same_key_within_3s"]))
print("  events with an xtables-monitor line (same destination, 3 s):", sum(1 for e in late if e["trace"]), "| of those with another try of the same key within 3 s:", sum(1 for e in late if e["trace"] and e["other_tries_same_key_within_3s"]))
for e in late:
    if len(e["tries_with_this_key"]) > 1 or len(e["packets_with_this_key"]) > 1 or e["status"] not in ("blocked",):
        print(f"  * {e['pod']} {e['pod_ip']}:{e['sport']} -> {e['addr']} t={e['t_ms']} | {e['status']}: {e['status_why']} | packets {[(p['ip_id'], p['verdict']) for p in e['packets_with_this_key']]} | tries {[(t['t'], t['class']) for t in e['tries_with_this_key']]} | xt lines {len(e['trace'])} | SYN-ACK {e.get('pcap_synack')} ICMP {e.get('pcap_icmp_unreachable')}")
print(f"late connections: {len(late)}; by runtime: " + str({rt: sum(1 for e in late if e['runtime'] == rt) for rt in ('kata', 'runc')}))
print("  with a trace line for the same destination:", sum(1 for e in late if e["trace"]), "| trace says blocked:", sum(1 for e in late if e["trace"] and all(" blocked " in x for x in e["trace"])), "| trace says passed:", sum(1 for e in late if any(" passed " in x for x in e["trace"])))
print("  with a conntrack NEW event:", sum(1 for e in late if e["conntrack_new"]))
print("  with packets in the pcap:", sum(1 for e in late if e.get("pcap")), "| SYN-ACK seen:", sum(1 for e in late if e.get("pcap_synack")), "| ICMP unreachable seen:", sum(1 for e in late if e.get("pcap_icmp_unreachable")))
print("  socket state after connect():", {s: sum(1 for e in late if e["socket"] == s) for s in sorted({e["socket"] for e in late})})
su = [e for e in events if e["kind"] == "startup"]
print(f"start-up connections sampled: {len(su)}; trace passed: {sum(1 for e in su if any(' passed ' in x for x in e['trace']))}; conntrack NEW: {sum(1 for e in su if e['conntrack_new'])}; SYN-ACK in pcap: {sum(1 for e in su if e.get('pcap_synack'))}; socket: " + str({s: sum(1 for e in su if e['socket'] == s) for s in sorted({e['socket'] for e in su})}))
