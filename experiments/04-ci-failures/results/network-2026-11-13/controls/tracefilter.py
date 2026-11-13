#!/usr/bin/env python3
"""2026-11-13, runs ON the VM as root. Reads `xtables-monitor --trace` (the nf_tables trace of every packet marked by the
TRACE rule in the raw table: TCP SYNs sent from pod addresses), groups the lines per packet (source address, source
port and IP id: the trace id changes between hooks, and the destination changes when a Service address is translated)
and writes
  - one summary line per packet to <out>/packets.log:
      P <epoch_ms> <src>:<sport> <dst>:<dport> <final dst>:<dport> <blocked|passed> <deciding filter chain> <trace lines>
  - the complete trace of every packet that no rule dropped or rejected to <out>/passed-traces.log, and of the first
    few blocked packets per source address to <out>/blocked-samples.log.
<epoch_ms> is when this process read the packet's first line (xtables-monitor is run line-buffered).
A REJECT rule shows in the trace as verdict DROP with the rule text "-j REJECT".
usage: stdbuf -oL xtables-monitor --trace | tracefilter.py <out-dir>"""
import os, re, sys, time
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
pk = open(f"{out}/packets.log", "a", buffering=1); passed = open(f"{out}/passed-traces.log", "a", buffering=1); samples = open(f"{out}/blocked-samples.log", "a", buffering=1)
live = {}; id2key = {}; sampled = {}; IDLE = 1.0; last_gc = time.time()
field = lambda line, k: (re.search(rf"\b{k}=(\S+)", line) or [None, "?"])[1]
def flush(key):
    p = live.pop(key); lines = p["lines"]; heads = [l for l in lines if l.startswith("PACKET:")]
    first, last = heads[0], heads[-1]; text = "\n".join(lines)
    blocked = bool(re.search(r"TRACE: \d+ \S+ \S+:(rule:0x[0-9a-f]+|policy):DROP", text))
    chains = re.findall(r"TRACE: \d+ \S+ filter:([^:]+):", text)
    m = re.findall(r"TRACE: \d+ \S+ filter:([^:]+):(?:rule:0x[0-9a-f]+|policy):(?:DROP|ACCEPT)", text)
    decide = m[-1] if m else (chains[-1] if chains else "-")
    head = f"{p['t']} {field(first, 'SRC')}:{field(first, 'SPORT')} {field(first, 'DST')}:{field(first, 'DPORT')} {field(last, 'DST')}:{field(last, 'DPORT')}"
    pk.write(f"P {head} {'blocked' if blocked else 'passed'} {decide} {len(lines)}\n")
    if not blocked: passed.write(f"### {head}\n{text}\n")
    elif sampled.get(field(first, "SRC"), 0) < 3:
        sampled[field(first, "SRC")] = sampled.get(field(first, "SRC"), 0) + 1; samples.write(f"### {head}\n{text}\n")
for line in sys.stdin:
    now = time.time(); line = line.strip(); f = line.split()
    if len(f) >= 3 and f[0] == "PACKET:":
        key = (field(line, "SRC"), field(line, "SPORT"), field(line, "ID")); id2key[f[2]] = key
        p = live.setdefault(key, {"t": int(now * 1000), "lines": []}); p["lines"].append(line); p["seen"] = now
    elif len(f) >= 3 and f[0] == "TRACE:" and f[2] in id2key and id2key[f[2]] in live:
        p = live[id2key[f[2]]]; p["lines"].append(line); p["seen"] = now
    if now - last_gc > 0.5:
        last_gc = now
        for key in [k for k, p in live.items() if now - p["seen"] > IDLE]: flush(key)
        if len(id2key) > 200000: id2key.clear()
for key in list(live): flush(key)
