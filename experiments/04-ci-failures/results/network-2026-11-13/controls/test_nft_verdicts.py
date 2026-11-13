#!/usr/bin/env python3
"""Synthetic test of nft-verdicts.py (review follow-up, 2026-11-13). One agent pod reuses source port 40000:
first for an ALLOWED try (gateway model port, connected), 100 s later for a LATE try to the metadata endpoint that the
probe logged as connected (v1 probe, socket not read) after that target had been blocked.
  case "leak":    the node ACCEPTED the second SYN  -> it must come out UNEXPLAINED (version 1 called it "allowed")
  case "no-leak": the node DROPPED the second SYN   -> one allowed SYN, nothing unexplained
  case "leak, no times": as "leak" but without conntrack events -> still UNEXPLAINED (the destination alone separates the tries)
  case "same destination": the port is reused for the SAME forbidden destination: once in the start-up window (connected),
                  once late and accepted; with times -> one start-up, one UNEXPLAINED; without times -> AMBIGUOUS, not "start-up"
usage: test_nft_verdicts.py   (writes its files under a temporary directory; prints PASS/FAIL per case; exit 1 on a failure)"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T0 = 1794560000000; IP = "10.42.0.50"
def pkt(i, ipid, pre, post, verdict):
    a, ap = pre.split(":"); b, bp = post.split(":"); hook = "FORWARD"
    L = [f'trace id aa{i:06x} ip raw PREROUTING packet: iif "cni0" ip saddr {IP} ip daddr {a} ip dscp cs0 ip ttl 64 ip id {ipid} ip length 60 tcp sport 40000 tcp dport {ap} tcp flags == syn',
         f'trace id bb{i:06x} ip filter {hook} packet: iif "cni0" ip saddr {IP} ip daddr {b} ip dscp cs0 ip ttl 63 ip id {ipid} ip length 60 tcp sport 40000 tcp dport {bp} tcp flags == syn',
         f'trace id bb{i:06x} ip filter {hook} rule counter packets 1 bytes 60 jump KUBE-ROUTER-FORWARD (verdict jump KUBE-ROUTER-FORWARD)']
    L.append(f'trace id bb{i:06x} ip filter KUBE-POD-FW-X rule reject (verdict drop)' if verdict == "drop" else f'trace id bb{i:06x} ip filter FLANNEL-FWD rule ip saddr 10.42.0.0/16 accept (verdict accept)')
    return L
def ctline(t, pre, post):
    a, ap = pre.split(":"); b, bp = post.split(":")
    return f"[{t / 1000:.6f}]\t    [NEW] tcp      6 120 SYN_SENT src={IP} dst={a} sport=40000 dport={ap} [UNREPLIED] src={b} dst={IP} sport={bp} dport=40000"
def run(name, packets, tries, cts, expect, forbid=()):
    d = tempfile.mkdtemp(prefix="nftv-"); os.makedirs(f"{d}/cap/trace"); os.makedirs(f"{d}/logs")
    open(f"{d}/raw.log", "w").write("\n".join(l for i, p in enumerate(packets) for l in pkt(i, *p)) + "\n")
    open(f"{d}/cap/conntrack-events.log", "w").write("\n".join(ctline(*c) for c in cts) + ("\n" if cts else ""))
    h = {"role": "agent", "runtime": "kata", "pod": "synthetic-agent", "pod_ip": IP, "t0_epoch_ms": T0, "allowed": ["gwm"],
         "targets": {"gwm": ["10.43.210.10:8080", "internal"], "gwpm": ["10.42.0.13:8080", "internal"], "meta": ["169.254.169.254:80", "external"]}}
    open(f"{d}/logs/synthetic-agent.log", "w").write("H " + json.dumps(h) + "\n" + "\n".join(f"A {T0 + dt} {lab} {res} 1 {port}" for dt, lab, res, port in tries) + "\n")
    r = subprocess.run([sys.executable, f"{HERE}/nft-verdicts.py", f"{d}/raw.log", f"{d}/out", f"{d}/cap", "-", f"{d}/logs"], capture_output=True, text=True)
    s = json.load(open(f"{d}/out-summary.json"))["accepted_by_class"] if r.returncode == 0 else {"error": r.stderr[-300:]}
    ok = all(s.get(k, 0) == v for k, v in expect.items()) and not any(k in s for k in forbid) and sum(s.values()) == sum(expect.values())
    print(("PASS" if ok else "FAIL"), name, "->", s); return ok
GW = ("10.43.210.10:8080", "10.42.0.13:8080"); MD = ("169.254.169.254:80", "169.254.169.254:80")
base = [(300, "meta", "t", 41000), (500, "meta", "t", 41002)]                       # the metadata target is blocked early in the pod
reuse = [(2000, "gwm", "o", 40000)] + base + [(102000, "meta", "o", 40000)]            # port 40000: allowed try, then a late "connected" try
ok = [
 run("leak", [(1, *GW, "accept"), (2, *MD, "accept")], reuse, [(T0 + 2001, *GW), (T0 + 102001, *MD)], {"allowed": 1, "UNEXPLAINED": 1}),
 run("no-leak", [(1, *GW, "accept"), (2, *MD, "drop")], reuse, [(T0 + 2001, *GW)], {"allowed": 1}, forbid=("UNEXPLAINED", "AMBIGUOUS")),
 run("leak, no times", [(1, *GW, "accept"), (2, *MD, "accept")], reuse, [], {"allowed (no packet time; matched on address, port and destination)": 1, "UNEXPLAINED": 1}),
 run("same destination, with times", [(1, *MD, "accept"), (2, *MD, "accept")], [(50, "meta", "o", 40000)] + base + [(102000, "meta", "o", 40000)],
     [(T0 + 51, *MD), (T0 + 102001, *MD)], {"start-up": 1, "UNEXPLAINED": 1}),
 run("same destination, no times", [(1, *MD, "accept"), (2, *MD, "accept")], [(50, "meta", "o", 40000)] + base + [(102000, "meta", "o", 40000)],
     [], {"AMBIGUOUS": 2}, forbid=("start-up",)),
]
print("ALL PASS" if all(ok) else "SOME FAILED"); sys.exit(0 if all(ok) else 1)
