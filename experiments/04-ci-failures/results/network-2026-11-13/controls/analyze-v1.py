#!/usr/bin/env python3
"""2026-11-13. Reads the probe logs (netwatch.py) and the host-side captures of one block and prints the tables of the report.
usage: analyze.py <data-dir> <no-churn start,end epoch ms> <churn start,end epoch ms>
data-dir: steady/*.log, batch/*.log (+ .pod.json, .init-netgate.log), t3lat/*, cap/{pod-events.jsonl, k3s-journal-netpol.log.gz,
trace/packets.log, conntrack-events.log}, t3-steady-apply.jsonl
A try is "forbidden" when its target is not in the pod's allowed list. For a pod whose policy exists before it starts, a
forbidden try that connects is "start-up" when the target had not been blocked yet in that pod, and "late" when it had."""
import bisect, datetime, glob, gzip, json, os, re, statistics, sys
D = sys.argv[1]; W = {"no churn": [int(x) for x in sys.argv[2].split(",")], "churn": [int(x) for x in sys.argv[3].split(",")]}
def load(path):
    h = None; rows = []; s = None
    for l in open(path, errors="replace"):
        if l.startswith("A "):
            f = l.split()
            if len(f) >= 6:   # st: the socket's TCP state after a connect() that returned no error (probe v2); None = not recorded (v1)
                st = int(f[6][3:]) if len(f) > 6 and f[6].startswith("st=") else None
                r = "f" if f[3] == "o" and st is not None and st != 1 else f[3]   # "f": connect() returned no error, but the socket was not ESTABLISHED
                rows.append((int(f[1]), f[2], r, int(f[4]), int(f[5]), st))
        elif l.startswith("H "): h = json.loads(l[2:])
        elif l.startswith("S "): s = json.loads(l[2:])
    return h, rows, s
zp = lambda p: p if os.path.exists(p) else p + ".gz"          # the published copy keeps the large logs compressed
zopen = lambda p: gzip.open(zp(p), "rt", errors="replace") if zp(p).endswith(".gz") else open(p, errors="replace")
def iso_ms(ts): return int(datetime.datetime.fromisoformat(ts).timestamp() * 1000)
# controller syncs from the journal
syncs = []; cur = None; triggers = []
jf = f"{D}/cap/k3s-journal-netpol.log.gz"
if os.path.exists(jf):
    for l in gzip.open(jf, "rt", errors="replace"):
        t = iso_ms(l.split()[0])
        if "Starting sync of iptables" in l: cur = {"start": t}
        elif "Restoring IPv4 iptables rules took" in l and cur: cur["restore_end"] = t
        elif "sync iptables took" in l and cur: cur["end"] = t; syncs.append(cur); cur = None
        elif "Received update to pod" in l or "Received pod" in l or "Received update for network policy" in l or "delete event" in l: triggers.append((t, l.split("] ", 1)[-1].strip()))
starts = [s["start"] for s in syncs]
def sync_context(t):
    i = bisect.bisect_right(starts, t) - 1
    if i >= 0 and syncs[i]["start"] <= t <= syncs[i]["end"]: return f"inside a sync ({t - syncs[i]['start']} ms after its start, {syncs[i]['end'] - t} ms before its end)"
    prev = f"{t - syncs[i]['end']} ms after the end of the previous sync" if i >= 0 else "no earlier sync"
    nxt = f"{syncs[i + 1]['start'] - t} ms before the next sync" if i + 1 < len(syncs) else "no later sync"
    return prev + ", " + nxt
events = [json.loads(l) for l in open(f"{D}/cap/pod-events.jsonl")] if os.path.exists(f"{D}/cap/pod-events.jsonl") else []
ev_t = [e["t_ms"] for e in events]
def pod_events_near(t, span=1000):
    a, b = bisect.bisect_left(ev_t, t - span), bisect.bisect_right(ev_t, t + span)
    names = sorted({f"{e.get('ns')}/{e.get('name')}" for e in events[a:b] if e.get("name")}); return len(names), names[:4]
ip_hist = {}
for e in events:
    if e.get("pod_ip"): ip_hist.setdefault(e["pod_ip"], {}).setdefault(f"{e['ns']}/{e['name']}", [e["t_ms"], e["t_ms"]])[1] = e["t_ms"]
trace = {}
if os.path.exists(zp(f"{D}/cap/trace/packets.log")):
    for l in zopen(f"{D}/cap/trace/packets.log"):
        f = l.split()
        if len(f) >= 8 and f[5] == "passed": trace.setdefault(f[2], []).append(l.strip())
ct = {}
if os.path.exists(zp(f"{D}/cap/conntrack-events.log")):
    for l in zopen(f"{D}/cap/conntrack-events.log"):
        if "[NEW]" in l:
            m = re.search(r"src=(\S+) dst=(\S+) sport=(\d+) dport=(\d+) (?:\[UNREPLIED\] )?src=(\S+)", l)
            if m: ct.setdefault(f"{m.group(1)}:{m.group(3)}", []).append(f"{l.split(']')[0].strip('[')} NEW {m.group(2)}:{m.group(4)} reply-src {m.group(5)}")
t3apply = {}
if os.path.exists(f"{D}/t3-steady-apply.jsonl"):
    for l in open(f"{D}/t3-steady-apply.jsonl"):
        r = json.loads(l)
        for p in r.get("pods", "").split(): t3apply[p] = r
CLASS = {}
def analyse_pod(path):
    h, rows, s = load(path)
    if not h: return None
    for k, v in h["targets"].items(): CLASS[k] = v[1]
    allowed = set(h.get("allowed", [])); name = h["pod"]; t0 = h["t0_epoch_ms"]; blocked_seen = {}; res = {"h": h, "rows": rows, "startup": [], "late": [], "false": [], "states": [], "name": name, "path": path}
    policy_from = t3apply[name]["apply_end_ms"] if name in t3apply else None
    for t, lab, r, d, sp, st in rows:
        if lab in allowed: continue
        if policy_from and t < policy_from: continue
        if r == "o": (res["late"] if lab in blocked_seen else res["startup"]).append((t, lab, sp)); res["states"].append(("late" if lab in blocked_seen else "startup", st))
        else:
            blocked_seen.setdefault(lab, t)
            if r == "f": res["false"].append((t, lab, sp))
    res["first_blocked"] = blocked_seen; return res
def fmt_t(t): return datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"
def describe(res, t, lab, sp):
    h = res["h"]; key = f"{h['pod_ip']}:{sp}"; n, names = pod_events_near(t)
    owners = sorted(ip_hist.get(h["pod_ip"], {}).items(), key=lambda kv: kv[1][0]); prev = [(o, v) for o, v in owners if not o.endswith("/" + h["pod"]) and v[0] < h["t0_epoch_ms"]]
    reuse = f"address used before by {prev[-1][0]} (last seen {(h['t0_epoch_ms'] - prev[-1][1][1]) / 1000:.1f} s before this pod's process started)" if prev else "address not used by an earlier pod in this capture"
    return (f"- {fmt_t(t)} `{h['pod']}` ({h['role']}, {h['runtime']}, {h['pod_ip']}) -> `{lab}` {h['targets'][lab][0]} ({CLASS[lab]}), source port {sp}, {(t - h['t0_epoch_ms']) / 1000:.2f} s after the process started\n"
            f"  - controller: {sync_context(t)}\n  - pod events within 1 s: {n} pod(s) {names}\n  - {reuse}\n"
            f"  - trace: {trace.get(key, ['no trace line for this source port (trace reader lost it or was restarting)'])}\n  - conntrack: {ct.get(key, ['no NEW event recorded'])}")
print(f"controller syncs in the journal: {len(syncs)}; duration ms min/median/max: " + (f"{min(s['end'] - s['start'] for s in syncs)}/{statistics.median(s['end'] - s['start'] for s in syncs):.0f}/{max(s['end'] - s['start'] for s in syncs)}" if syncs else "-"))
for wn, (a, b) in W.items():
    inw = [s for s in syncs if a <= s["start"] <= b]; evw = [e for e in events if a <= e["t_ms"] <= b and e.get("ns") not in ("kube-system",)]
    print(f"window '{wn}' {fmt_t(a)} to {fmt_t(b)}: {len(inw)} syncs, {len(evw)} pod events outside kube-system, {len({e['name'] for e in evw})} distinct pods")
# ---- steady state
print("\n## Steady state\n")
steady = [r for r in (analyse_pod(p) for p in sorted(glob.glob(f"{D}/steady*/*.log"))) if r]
print("Probe v1 (the eight pods named steady-*) recorded only that connect() returned without an error; probe v2 (steady2-*) also read the")
print("socket: 'established' = TCP state ESTABLISHED with a peer, 'false success' = connect() returned no error but the socket was CLOSE with ECONNREFUSED pending.\n")
print("| Window | Pod | Probe | Runtime | Target class | Forbidden tries | connect() returned no error, socket not read (v1) | established (v2) | false success (v2) |"); print("|---|---|---|---|---|---|---|---|---|")
tot = {}
for wn, (a, b) in W.items():
    for res in steady:
        h = res["h"]; allowed = set(h.get("allowed", [])); pf = t3apply.get(h["pod"], {}).get("apply_end_ms", 0) + 5000 if h["pod"] in t3apply else h["t0_epoch_ms"] + 5000; v = h.get("probe_version", 1)
        for cls in ("internal", "external"):
            tries = [(t, lab, r) for t, lab, r, d, sp, st in res["rows"] if a <= t <= b and t >= pf and lab not in allowed and CLASS[lab] == cls]
            if not tries: continue
            op = sum(1 for x in tries if x[2] == "o"); fa = sum(1 for x in tries if x[2] == "f"); k = (wn, h["runtime"], f"v{v}", cls); tot.setdefault(k, [0, 0, 0]); tot[k][0] += len(tries); tot[k][1] += op; tot[k][2] += fa
            print(f"| {wn} | {h['pod']} | v{v} | {h['runtime']} | {cls} | {len(tries)} | {op if v == 1 else '-'} | {op if v > 1 else '-'} | {fa if v > 1 else '-'} |")
print("\n| Window | Runtime | Probe | Target class | Forbidden tries | connect() returned no error (v1) | established (v2) | false success (v2) |"); print("|---|---|---|---|---|---|---|---|")
for (wn, rt, v, cls), (n, o, fa) in sorted(tot.items()): print(f"| {wn} | {rt} | {v} | {cls} | {n} | {o if v == 'v1' else '-'} | {o if v != 'v1' else '-'} | {fa if v != 'v1' else '-'} |")
print("\nPer target, both windows, all steady pods (forbidden tries / connected):")
pt = {}
for res in steady:
    allowed = set(res["h"].get("allowed", [])); pf = t3apply.get(res["h"]["pod"], {}).get("apply_end_ms", 0) + 5000 if res["h"]["pod"] in t3apply else res["h"]["t0_epoch_ms"] + 5000
    for t, lab, r, d, sp, st in res["rows"]:
        if lab in allowed or t < pf: continue
        for wn, (a, b) in W.items():
            if a <= t <= b: k = (wn, lab); pt.setdefault(k, [0, 0]); pt[k][0] += 1; pt[k][1] += r == "o"
for (wn, lab), (n, o) in sorted(pt.items()): print(f"- {wn}: {lab} ({CLASS[lab]}) {n} / {o}")
print("\n### Late connections in the steady pods (connect() returned no error on a forbidden target after it had been blocked in that pod; v2 pods: only tries whose socket was ESTABLISHED)\n")
nl = 0
for res in steady:
    for t, lab, sp in res["late"]: nl += 1; print(describe(res, t, lab, sp))
print(f"\ntotal late connections in steady pods: {nl}")
def state_tally(pods, kind):
    c = {}
    for res in pods:
        for k, st in res["states"]:
            if k == kind: key = {None: "not recorded (probe v1)", 1: "ESTABLISHED", 7: "CLOSE"}.get(st, f"state {st}"); c[key] = c.get(key, 0) + 1
    return c
print("socket state right after connect() returned, late connections:", state_tally(steady, "late"), "| start-up connections:", state_tally(steady, "startup"))
# host-side count that does not depend on the probe: connections the firewall let through (conntrack NEW, trace "passed")
print("\n### What the host recorded for the steady pods after their first 5 s (independent of what connect() returned)\n")
# A trace counts as "passed" only when it contains a final ACCEPT of the filter table: the accepting rule of FLANNEL-FWD,
# KUBE-NWPLCY-TAIL or KUBE-FORWARD, or the policy of INPUT. (A line "FORWARD policy ACCEPT" printed before the rule
# lines is not one: see nft-verdicts.py; the LAST filter line of the trace must be the accept.) The
# reader lost lines whenever xtables-monitor restarted; a trace cut before the pod's chain has neither a drop nor an
# accept line and is counted as incomplete.
complete = set(); opener = open
for cand in (f"{D}/cap/trace/passed-traces.log", f"{D}/cap/trace/passed-traces.log.gz"):
    if os.path.exists(cand):
        key = None; lastf = ""; nf = 0
        def close(key, lastf, nf):
            if key and re.search(r" filter:(FLANNEL-FWD|KUBE-NWPLCY-TAIL|KUBE-FORWARD):rule:0x[0-9a-f]+:ACCEPT| filter:INPUT:policy:ACCEPT", lastf) and (nf >= 2 or "policy" not in lastf): complete.add(key)   # a policy line alone is the stray first line
        for l in (gzip.open(cand, "rt", errors="replace") if cand.endswith(".gz") else open(cand, errors="replace")):
            if l.startswith("### ") and not l.startswith("### restart"): close(key, lastf, nf); f = l.split(); key = (f[1], f[2]); lastf = ""; nf = 0
            elif " filter:" in l: lastf = l; nf += 1
        close(key, lastf, nf)
print("| Pod | Runtime | conntrack NEW events to allowed destinations | conntrack NEW events to forbidden destinations | traced SYNs to forbidden destinations: passed | blocked | incomplete trace |"); print("|---|---|---|---|---|---|---|")
ctall = {}; trall = {}
if os.path.exists(zp(f"{D}/cap/conntrack-events.log")):
    for l in zopen(f"{D}/cap/conntrack-events.log"):
        if "[NEW]" not in l: continue
        m = re.search(r"\[(\d+\.\d+)\].*?src=(\S+) dst=(\S+) sport=\d+ dport=(\d+)", l)
        if m: ctall.setdefault(m.group(2), []).append((float(m.group(1)) * 1000, f"{m.group(3)}:{m.group(4)}"))
if os.path.exists(zp(f"{D}/cap/trace/packets.log")):
    for l in zopen(f"{D}/cap/trace/packets.log"):
        f = l.split()
        if len(f) >= 8: trall.setdefault(f[2].rsplit(":", 1)[0], []).append((int(f[1]), f[3], f[5] if f[5] == "blocked" else ("passed" if (f[1], f[2]) in complete else "incomplete")))
for res in steady:
    h = res["h"]; ok = {h["targets"][l][0] for l in h.get("allowed", [])}; pf = t3apply.get(h["pod"], {}).get("apply_end_ms", 0) + 5000 if h["pod"] in t3apply else h["t0_epoch_ms"] + 5000
    end = max((r[0] for r in res["rows"]), default=pf)
    c = [(t, d) for t, d in ctall.get(h["pod_ip"], []) if pf <= t <= end]; tr = [(t, d, v) for t, d, v in trall.get(h["pod_ip"], []) if pf <= t <= end]
    print(f"| {h['pod']} | {h['runtime']} | {sum(1 for t, d in c if d in ok)} | {sum(1 for t, d in c if d not in ok)} | {sum(1 for t, d, v in tr if v == 'passed' and d not in ok)} | {sum(1 for t, d, v in tr if v == 'blocked' and d not in ok)} | {sum(1 for t, d, v in tr if v == 'incomplete' and d not in ok)} |")
print("\n### Start of the steady pods\n")
for res in steady:
    h = res["h"]; su = res["startup"]
    print(f"- `{h['pod']}` ({h['runtime']}): {len(su)} forbidden tries connected before the first block; last at {max((t for t, _, _ in su), default=h['t0_epoch_ms']) - h['t0_epoch_ms']} ms; targets {sorted({l for _, l, _ in su})}")
# ---- start-up batch
print("\n## Start-up batch\n")
batch = {}
for p in sorted(glob.glob(f"{D}/batch/*.log")):
    if ".init-" in p: continue
    res = analyse_pod(p)
    if not res: continue
    m = re.match(r"b-(\w+)-(kn|kg|rn)-\d+", res["name"])
    if not m: continue
    pj = json.load(open(p[:-4] + ".pod.json")) if os.path.exists(p[:-4] + ".pod.json") else {}
    res["apply_end"] = pj.get("apply_end_ms"); g = p[:-4] + ".init-netgate.log"; res["gate"] = None
    if os.path.exists(g):
        mm = re.search(r"NETGATE (\{.*\})", open(g).read()); res["gate"] = json.loads(mm.group(1)) if mm else None
    batch.setdefault((m.group(2), m.group(1)), []).append(res)
ARM = {"kn": "Kata, no gate", "kg": "Kata, gate", "rn": "runc, no gate"}
print("| Arm | Pod kind | Pods | Pods where a forbidden target connected (ESTABLISHED) | Forbidden tries ESTABLISHED / all | Last connected, ms after process start (min / median / max) | Pods with a late ESTABLISHED connection | False successes (socket CLOSE, ECONNREFUSED) | apply -> main process start, s (median) | Gate wait, s (median / max) |"); print("|---|---|---|---|---|---|---|---|---|---|")
for (arm, kind), L in sorted(batch.items()):
    leak = [r for r in L if r["startup"] or r["late"]]; lasts = [max(t for t, _, _ in r["startup"] + r["late"]) - r["h"]["t0_epoch_ms"] for r in leak]
    allf = sum(1 for r in L for t, lab, rr, d, sp, st in r["rows"] if lab not in set(r["h"].get("allowed", []))); conn = sum(len(r["startup"]) + len(r["late"]) for r in L)
    st = [(r["h"]["t0_epoch_ms"] - r["apply_end"]) / 1000 for r in L if r.get("apply_end")]; gw = [r["gate"]["waited_s"] for r in L if r.get("gate")]
    print(f"| {ARM[arm]} | {kind} | {len(L)} | {len(leak)} | {conn} / {allf} | " + (f"{min(lasts)} / {statistics.median(lasts):.0f} / {max(lasts)}" if lasts else "-") +
          f" | {sum(1 for r in L if r['late'])} | {sum(len(r['false']) for r in L)} in {sum(1 for r in L if r['false'])} pods | " + (f"{statistics.median(st):.1f}" if st else "-") + " | " + (f"{statistics.median(gw):.2f} / {max(gw):.2f}" if gw else "-") + " |")
# does the end of each pod's window coincide with the controller writing the rules?
restores = sorted(s["restore_end"] for s in syncs if "restore_end" in s)
trig = {}
for t, text in triggers:
    m = re.search(r"Received update to pod: (\S+)", text)
    if m: trig.setdefault(m.group(1).split("/")[-1], []).append(t)
print("\n### End of the start-up window against the controller's rule writes (pods without the gate that had a window)\n")
print("| Arm | Pod kind | Pods with a window | ...where every target's last connection and first block bracket one rule restore (+-60 ms) | First block minus that restore's end, ms (min / median / max) | Process start minus the first 'Received update to pod' for this pod, ms (median) | Restore end minus that first update, ms (median) |"); print("|---|---|---|---|---|---|---|")
for (arm, kind), L in sorted(batch.items()):
    if arm == "kg": continue
    n = ok = 0; deltas = []; lead = []; lat = []
    for res in L:
        if not res["startup"]: continue
        n += 1; good = True; fbmin = None
        for lab in {l for _, l, _ in res["startup"]}:
            lo = max(t for t, l, _ in res["startup"] if l == lab); fb = res["first_blocked"].get(lab)
            if fb is None: good = False; continue
            i = bisect.bisect_right(restores, fb + 60) - 1
            if i < 0 or restores[i] < lo - 60: good = False
            else: deltas.append(fb - restores[i]); fbmin = restores[i] if fbmin is None else min(fbmin, restores[i])
        ok += good; tr0 = trig.get(res["name"])
        if tr0: lead.append(res["h"]["t0_epoch_ms"] - tr0[0])
        if tr0 and fbmin: lat.append(fbmin - tr0[0])
    print(f"| {ARM[arm]} | {kind} | {n} | {ok} | " + (f"{min(deltas)} / {statistics.median(deltas):.0f} / {max(deltas)}" if deltas else "-") + " | " + (f"{statistics.median(lead):.0f}" if lead else "-") + " | " + (f"{statistics.median(lat):.0f}" if lat else "-") + " |")
allb = [r for L in batch.values() for r in L]
print("\nsocket state right after connect() returned, batch pods: late connections:", state_tally(allb, "late"), "| start-up connections:", state_tally(allb, "startup"))
print("\n### Late connections in the batch pods\n")
for L in batch.values():
    for res in L:
        for t, lab, sp in res["late"]: print(describe(res, t, lab, sp))
print("\n### Gate arm: every forbidden connection seen by the main container\n")
for (arm, kind), L in sorted(batch.items()):
    if arm != "kg": continue
    for res in L:
        for t, lab, sp in res["startup"] + res["late"]: print(describe(res, t, lab, sp))
print("\n### Gate results that were not ok, and what the gate saw before it passed\n")
seen = {}
for (arm, kind), L in sorted(batch.items()):
    for res in L:
        g = res.get("gate")
        if arm == "kg" and (not g or not g.get("ok")): print(f"- {res['name']}: {g}")
        if g: seen.setdefault(kind, []).append(len(g.get("reachable_before", {})) > 0)
for k, v in seen.items(): print(f"- {k}: the gate itself reached a forbidden canary before passing in {sum(v)} of {len(v)} pods")
# ---- T3 latency
print("\n## T3: policy applied to a running pod\n")
ap = {}
if os.path.exists(f"{D}/t3lat/apply-times.jsonl"):
    for l in open(f"{D}/t3lat/apply-times.jsonl"):
        r = json.loads(l)
        if "pods" in r: ap[r["pods"].strip()] = r
print("| Pod | Runtime | apply took, ms | Last forbidden connection, ms after `kubectl apply` returned (after it started) | Targets open before the apply | connect() without error after the first block (v1 probe: socket not read; v2: ESTABLISHED only) |"); print("|---|---|---|---|---|---|")
for p in sorted(glob.glob(f"{D}/t3lat/t3lat-*.log")) + sorted(glob.glob(f"{D}/steady/steady-t3-*.log")):
    h, rows, s = load(p)
    if not h or h["pod"] not in {**ap, **t3apply}: continue
    a = {**ap, **t3apply}[h["pod"]]; before = sorted({lab for t, lab, r, d, sp, st in rows if t < a["apply_start_ms"] and r == "o"})
    fb = {}; late = 0; last = None      # last connection of each target BEFORE its first block; later "connections" counted apart
    for t, lab, r, d, sp, st in rows:
        if lab not in before: continue
        if t >= a["apply_start_ms"] and r != "o": fb.setdefault(lab, t)
        elif r == "o" and lab in fb: late += 1
        elif r == "o": last = t if last is None else max(last, t)
    print(f"| {h['pod']} | {h['runtime']} | {a['apply_end_ms'] - a['apply_start_ms']} | {last - a['apply_end_ms'] if last else '-'} ({last - a['apply_start_ms'] if last else '-'}) | {', '.join(before)} | {late} |")
