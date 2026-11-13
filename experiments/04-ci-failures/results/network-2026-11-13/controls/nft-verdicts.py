#!/usr/bin/env python3
"""2026-11-13, runs ON the VM. Version 2 (review follow-up; version 1 is kept as nft-verdicts-v1.py).

Host-side check that does not depend on what connect() returned in the pods: the raw `nft monitor trace` of every TCP SYN
from a pod address, the filter-table verdict the kernel reported for each (drop = the REJECT rules, accept), and for
every ACCEPTED SYN the probe try it belongs to.

What version 1 did wrong: it joined an accepted SYN to probe tries by (source address, source port) only, and any
"allowed" try with that pair made the SYN "allowed". A pod reuses source ports for other destinations, so an accepted
SYN to a forbidden destination could inherit the class of another try. Version 2:
  - joins on source address, source port AND destination (the destination BEFORE Service translation, taken from the
    packet's own PREROUTING trace line; the probe logs that address), and on time: the SYN belongs to the try with the
    same three fields whose logged time is closest to the packet's time, within TOLERANCE_MS;
  - the packet's time comes from the conntrack NEW event of the same connection (same three fields; the n-th accepted
    SYN of a key is paired with the n-th NEW event of that key, only when the counts are equal), else from the
    xtables-monitor summary line of the same three fields (same pairing rule), else the packet has no time and is
    matched on the three fields only;
  - never resolves a doubt in favour of "allowed": tries of different classes that time cannot separate -> AMBIGUOUS;
    no try with that destination -> explained only by a rule that uses the packet's time (below), else UNEXPLAINED.
Classes of an accepted SYN:
  allowed          its try went to a destination the pod's policy allows
  start-up         its try connected (v2 probe: socket ESTABLISHED) before that target was first blocked in the pod
  start-up, try not completed   its try did not connect in the probe (timeout), and the packet's time is not later than the
                   pod's last start-up connection (+100 ms): accepted by the node inside the window
  pre-policy       T3 pods: the try is earlier than the end of `kubectl apply` + 5 s
  guest port 4460  no probe target; from a Kata pod's address; time not later than the pod's last start-up connection
                   (+300 ms) or before the container's process started
  gate canary      no probe try; a gated pod; destination is one of the gate's canaries; time before the main process started
  AMBIGUOUS / UNEXPLAINED   everything else; each is written to <out>-examined.jsonl with conntrack, pcap and probe evidence
usage: nft-verdicts.py <raw-nft-trace.log> <out-prefix> <cap-dir> <t3-apply.jsonl or -> <log-dir>..."""
import glob, gzip, json, os, re, subprocess, sys
raw, outp, cap, t3f = sys.argv[1:5]; dirs = sys.argv[5:]; TOLERANCE_MS = 1000
zo = lambda p: gzip.open(p + ".gz", "rt", errors="replace") if not os.path.exists(p) and os.path.exists(p + ".gz") else open(p, errors="replace")
pk = re.compile(r"ip saddr (\S+) ip daddr (\S+) .*ip id (\d+) .*tcp sport (\d+) tcp dport (\d+)")
# ---- 1. the nft trace: one record per packet (merged by addresses, ports and IP id; a drop anywhere wins)
pre = {}; key = {}; rec = {}; early_policy = 0; n = 0
with open(raw, errors="replace") as f:
    for l in f:
        if not l.startswith("trace id "): continue
        if " packet: " in l:
            m = pk.search(l)
            if not m: continue
            src, dst, ipid, sp, dp = m.group(1), f"{m.group(2)}:{m.group(5)}", int(m.group(3)), int(m.group(4)), m.group(5)
            if " ip raw PREROUTING " in l: pre[(src, sp, ipid)] = dst; continue
            if " ip filter " not in l: continue
            k = (src, sp, ipid, dst); key[l[9:17]] = k
            if k not in rec: rec[k] = {"seq": n, "pre": pre.pop((src, sp, ipid), None), "v": "no verdict line"}; n += 1
        elif " ip filter " in l:
            k = key.get(l[9:17])
            if k is None: continue
            r = rec[k]
            if "verdict drop" in l: r["v"] = "drop"
            elif "policy accept" in l and r["v"] == "no verdict line": r["v"] = "chain policy accept"; early_policy += 1
            elif "verdict accept" in l and r["v"] != "drop": r["v"] = "accept"
tot = {}
for r in rec.values(): tot[r["v"]] = tot.get(r["v"], 0) + 1
print("SYNs from pod addresses seen at the filter table:", len(rec), tot, "| packets with a policy-accept line as first verdict line:", early_policy)
accepted = sorted(((k, r) for k, r in rec.items() if r["v"] in ("accept", "chain policy accept")), key=lambda kr: kr[1]["seq"])
# ---- 2. packet times: conntrack NEW events and xtables-monitor summaries, keyed by (src, sport, destination before translation)
ct = {}; ct_post = {}
for l in zo(f"{cap}/conntrack-events.log"):
    if "[NEW]" not in l: continue
    m = re.search(r"\[(\d+\.\d+)\].*?src=(\S+) dst=(\S+) sport=(\d+) dport=(\d+) (?:\[UNREPLIED\] )?src=(\S+) dst=\S+ sport=(\d+)", l)
    if m:
        t = float(m.group(1)) * 1000
        ct.setdefault((m.group(2), int(m.group(4)), f"{m.group(3)}:{m.group(5)}"), []).append(t)
        ct_post.setdefault((m.group(2), int(m.group(4)), f"{m.group(6)}:{m.group(7)}"), []).append(t)
xt = {}
if os.path.exists(f"{cap}/trace/packets.log") or os.path.exists(f"{cap}/trace/packets.log.gz"):
    for l in zo(f"{cap}/trace/packets.log"):
        f = l.split()
        if len(f) >= 8 and f[5] != "blocked":
            s, p = f[2].rsplit(":", 1); xt.setdefault((s, int(p), f[3]), []).append(float(f[1]))
groups = {}
for (src, sp, ipid, post), r in accepted: groups.setdefault((src, sp, r["pre"] or post, r["pre"] is None), []).append(r)
for (src, sp, dst, nopre), rs in groups.items():
    for name, table in (("conntrack", ct_post if nopre else ct), ("xtables-monitor", {} if nopre else xt)):
        ts = table.get((src, sp, dst), [])
        if ts and len(ts) == len(rs):
            for r, t in zip(rs, ts): r["t"] = t; r["t_from"] = name
            break
# ---- 3. the probe tries
t3 = {}
for fp in [t3f] + [os.path.join(d, "apply-times.jsonl") for d in dirs]:
    if fp != "-" and os.path.exists(fp):
        for l in open(fp):
            j = json.loads(l)
            for p in j.get("pods", "").split(): t3[p] = j["apply_end_ms"] + 5000
gate = {}
for d in dirs:
    for p in glob.glob(os.path.join(d, "*.pod.json")):
        try: j = json.load(open(p)); gate[j["plan"]["name"]] = bool(j["plan"].get("gate"))
        except Exception: pass
tries = {}; pods = {}
for d in dirs:
    for p in sorted(glob.glob(os.path.join(d, "*.log"))):
        if ".init-" in p or "driver" in p: continue
        h = None; blocked = set()
        for l in open(p, errors="replace"):
            if l.startswith("H "):
                h = json.loads(l[2:]); allowed = set(h.get("allowed", [])); pf = t3.get(h["pod"], 0); T = h["targets"]
                P = pods.setdefault(h["pod_ip"], []); me = {"pod": h["pod"], "runtime": h["runtime"], "t0": h["t0_epoch_ms"], "window_end": None, "gate": gate.get(h["pod"], False), "end": h["t0_epoch_ms"]}; P.append(me)
                dnat = {T[a][0]: T[b][0] for a, b in (("api", "node6443"), ("gwm", "gwpm"), ("gwa", "gwpa")) if a in T and b in T}
                continue
            if not l.startswith("A ") or not h: continue
            f = l.split()
            if len(f) < 6: continue
            t = int(f[1]); lab = f[2]; est = f[3] == "o" and (len(f) < 7 or f[6] == "st=1"); me["end"] = t
            if lab in allowed: c = "allowed"
            elif t < pf: c = "pre-policy"
            elif est and lab not in blocked: c = "start-up"; me["window_end"] = t
            else:
                c = "blocked-or-late"; blocked.add(lab)
            e = {"t": t, "pod": h["pod"], "target": lab, "class": c, "result": " ".join(f[3:5] + f[6:])}
            tries.setdefault((h["pod_ip"], int(f[5]), T[lab][0]), []).append(e)
            if T[lab][0] in dnat: tries.setdefault((h["pod_ip"], int(f[5]), "post:" + dnat[T[lab][0]]), []).append(e)
probe_ips = set(pods)
def owner(ip, t):
    c = pods.get(ip, [])
    if len(c) == 1 or t is None: return c[0] if len(c) == 1 else None
    c = [q for q in c if q["t0"] - 60000 <= t <= q["end"] + 5000]
    return min(c, key=lambda q: abs(q["t0"] - t)) if c else None
CANARY_PORTS = {"443", "80", "10250", "6443"}
def classify(src, sp, r, post):
    t = r.get("t"); dst = r["pre"]; cands = tries.get((src, sp, dst), []) if dst else tries.get((src, sp, post), []) + tries.get((src, sp, "post:" + post), [])
    q = owner(src, t); shown = dst or post
    if not cands:
        port = shown.rsplit(":", 1)[1]
        if port == "4460" and q and q["runtime"] == "kata" and t is not None and (t < q["t0"] or (q["window_end"] and t <= q["window_end"] + 300)):
            return "guest port 4460 (" + ("before the container's process started" if t < q["t0"] else "inside the start-up window") + ")", None
        if q and q["gate"] and port in CANARY_PORTS and t is not None and t < q["t0"]: return "gate canary (before the main process started)", None
        return ("UNEXPLAINED: no probe try to this destination" if t is not None else "AMBIGUOUS: no probe try to this destination and no packet time"), None
    if t is None:
        cl = {c["class"] for c in cands}
        if len(cl) > 1: return "AMBIGUOUS: tries of different classes, no packet time", None
        c = cands[0]
        return (c["class"] + " (no packet time; matched on address, port and destination)" if c["class"] != "blocked-or-late" else "UNEXPLAINED: accepted, but the only tries with this address, port and destination were blocked or late (no packet time)"), c
    best = min(cands, key=lambda c: abs(c["t"] - t))
    if abs(best["t"] - t) > TOLERANCE_MS: return f"UNEXPLAINED: nearest try with this address, port and destination is {abs(best['t'] - t):.0f} ms away", best
    if any(c["class"] != best["class"] and abs(c["t"] - t) <= TOLERANCE_MS for c in cands): return "AMBIGUOUS: tries of different classes within the tolerance", best
    if best["class"] != "blocked-or-late": return best["class"], best
    if q and q["window_end"] and t <= q["window_end"] + 100: return "start-up, try not completed in the probe", best
    return "UNEXPLAINED: accepted by the node, but the probe try was blocked or late", best
cls = {}; examine = []; timed = {}
with open(outp + "-accepted.txt", "w") as o:
    for (src, sp, ipid, post), r in accepted:
        if src not in probe_ips: c, best = "not a probe pod's address", None
        else: c, best = classify(src, sp, r, post)
        c2 = c.split(":")[0] if c.startswith(("UNEXPLAINED", "AMBIGUOUS")) else c
        cls[c2] = cls.get(c2, 0) + 1; timed[r.get("t_from", "no time")] = timed.get(r.get("t_from", "no time"), 0) + 1
        o.write(f"{src}:{sp} -> {r['pre'] or '?'} (after translation {post}) ipid {ipid} [{r['v']}] t={r.get('t', '-')} ({r.get('t_from', 'no time')}) :: {c} :: {best or ''}\n")
        if c.startswith(("UNEXPLAINED", "AMBIGUOUS")): examine.append({"src": src, "sport": sp, "dst": r["pre"], "dst_after_translation": post, "ip_id": ipid, "verdict": r["v"], "t_ms": r.get("t"), "t_from": r.get("t_from"), "class": c, "nearest_try": best})
print("accepted SYNs, time source:", timed)
print("accepted SYNs by class:", dict(sorted(cls.items())))
# ---- 4. every unexplained or ambiguous one, examined
pcap = f"{cap}/cni0-syn-rst-icmp.pcap"
for e in examine:
    q = owner(e["src"], e["t_ms"]); e["pod"] = q and {k: q[k] for k in ("pod", "runtime", "gate", "t0", "window_end")}
    e["all_tries_with_this_address_and_port"] = [c for (ip, sp, d), L in tries.items() if ip == e["src"] and sp == e["sport"] and not d.startswith("post:") for c in L][:8]
    keyc = (e["src"], e["sport"], e["dst"] or e["dst_after_translation"]); e["conntrack_new_times"] = (ct if e["dst"] else ct_post).get(keyc, [])
    if os.path.exists(pcap):
        out = subprocess.run(["tcpdump", "-r", pcap, "-n", "-tt", f"host {e['src']} and tcp port {e['sport']}"], capture_output=True, text=True).stdout.splitlines()
        near = [x for x in out if e["t_ms"] is None or abs(float(x.split()[0]) * 1000 - e["t_ms"]) < 3000]
        e["pcap"] = [x[:200] for x in near][:10]; e["pcap_synack_to_the_pod"] = sum(1 for x in near if "Flags [S.]" in x)
    else: e["pcap"] = "no pcap for this capture"
with open(outp + "-examined.jsonl", "w") as o:
    for e in examine: o.write(json.dumps(e) + "\n")
print(f"unexplained or ambiguous accepted SYNs: {len(examine)} (each in {os.path.basename(outp)}-examined.jsonl)")
for e in examine[:60]: print("  ", e["src"], e["sport"], "->", e["dst"] or e["dst_after_translation"], "|", e["class"], "| t", e["t_ms"], "| pod", e["pod"] and e["pod"]["pod"], "| SYN-ACK in pcap:", e.get("pcap_synack_to_the_pod"), "| tries:", [(c["target"], c["class"], c["result"]) for c in e["all_tries_with_this_address_and_port"]][:4])
nov = sum(1 for k, r in rec.items() if r["v"] == "no verdict line" and k[0] in probe_ips)
print("SYNs from probe pod addresses with no verdict line in the trace (trace events lost):", nov)
json.dump({"filter_table_syns": len(rec), "verdicts": tot, "accepted_by_class": cls, "accepted_time_source": timed, "examined": len(examine), "no_verdict_from_probe_pods": nov, "tolerance_ms": TOLERANCE_MS}, open(outp + "-summary.json", "w"), indent=1)
