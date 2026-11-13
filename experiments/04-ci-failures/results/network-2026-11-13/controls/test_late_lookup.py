#!/usr/bin/env python3
"""Synthetic test of late-lookup.py version 3 (second review correction, 2026-11-13). One Kata executor pod; source port
40000 is used more than once for the SAME forbidden destination (metadata endpoint). The late event is the last try,
where connect() returned no error after the target had been blocked. No xtables-monitor lines and no pcap, so the nft
path decides.
  reviewer's case        an old try whose packet was REJECTED, then the late try whose packet was ACCEPTED (different IP ids),
                         with its conntrack NEW event            -> must be ACCEPTED, never blocked (version 2: "blocked")
  same, no conntrack     the same two packets, no conntrack file entry -> ACCEPTED by order (2 tries, 2 packets), not blocked
  all dropped            both packets rejected                    -> blocked (every packet of this key was dropped)
  one and one            a single try and a single rejected packet -> blocked
  window then late       a start-up try accepted (conntrack NEW at that time), the late try's packet rejected
                                                                 -> blocked, separated by conntrack
  cannot separate        three tries, two packets (one accepted, one rejected), no timed source -> inconclusive
usage: test_late_lookup.py   (temporary files; prints PASS/FAIL per case; exit 1 on a failure)"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T0 = 1794560000000; IP = "10.42.0.60"; MD = "169.254.169.254"
def pkt(i, ipid, verdict):
    base = f'ip saddr {IP} ip daddr {MD} ip dscp cs0 ip ttl 64 ip id {ipid} ip length 60 tcp sport 40000 tcp dport 80 tcp flags == syn'
    return [f'trace id aa{i:06x} ip raw PREROUTING packet: iif "cni0" {base}', f'trace id aa{i:06x} ip raw PREROUTING policy accept',
            f'trace id bb{i:06x} ip filter FORWARD packet: iif "cni0" oif "ens4" {base}',
            f'trace id bb{i:06x} ip filter FORWARD rule counter packets 1 bytes 60 jump KUBE-ROUTER-FORWARD (verdict jump KUBE-ROUTER-FORWARD)',
            f'trace id bb{i:06x} ip filter KUBE-POD-FW-X rule reject (verdict drop)' if verdict == "drop" else f'trace id bb{i:06x} ip filter FLANNEL-FWD rule ip saddr 10.42.0.0/16 accept (verdict accept)']
def run(name, packets, tries, ct_times, want, why=""):
    d = tempfile.mkdtemp(prefix="latel-"); os.makedirs(f"{d}/cap/trace"); os.makedirs(f"{d}/logs")
    open(f"{d}/cap/trace/raw-nft-trace.log", "w").write("\n".join(l for i, p in enumerate(packets) for l in pkt(i, *p)) + "\n")
    open(f"{d}/cap/trace/packets.log", "w").write("")
    open(f"{d}/cap/conntrack-events.log", "w").write("".join(f"[{(T0 + t) / 1000:.6f}]\t    [NEW] tcp      6 120 SYN_SENT src={IP} dst={MD} sport=40000 dport=80 [UNREPLIED] src={MD} dst={IP} sport=80 dport=40000\n" for t in ct_times))
    h = {"role": "exec-repro", "runtime": "kata", "pod": "synthetic-exec", "pod_ip": IP, "t0_epoch_ms": T0, "allowed": [], "targets": {"meta": [f"{MD}:80", "external"]}}
    open(f"{d}/logs/synthetic-exec.log", "w").write("H " + json.dumps(h) + "\n" + "\n".join(f"A {T0 + dt} meta {res} 1 {port}" for dt, res, port in tries) + "\n")
    r = subprocess.run([sys.executable, f"{HERE}/late-lookup.py", f"{d}/cap", "-", f"{d}/out.jsonl", f"{d}/logs"], capture_output=True, text=True)
    ev = [json.loads(l) for l in open(f"{d}/out.jsonl")] if r.returncode == 0 else []
    late = [e for e in ev if e["kind"] == "late"]
    got = (late[-1]["status"], late[-1]["status_why"]) if late else ("error", r.stderr[-300:])
    ok = got[0] == want and why in got[1]
    print(("PASS" if ok else "FAIL"), name, "->", got[0] + ":", got[1][:150]); return ok
block = [(600, "t", 41000)]      # another port: the target is blocked in the pod before the late try
ok = [
 run("reviewer's case", [(1, "drop"), (2, "accept")], [(300, "t", 40000)] + block + [(102000, "o", 40000)], [102001], "ACCEPTED", "conntrack NEW"),
 run("same, no conntrack", [(1, "drop"), (2, "accept")], [(300, "t", 40000)] + block + [(102000, "o", 40000)], [], "ACCEPTED", "by order"),
 run("all dropped", [(1, "drop"), (2, "drop")], [(300, "t", 40000)] + block + [(102000, "o", 40000)], [], "blocked", "every packet of this key was dropped"),
 run("one and one", [(2, "drop")], block + [(102000, "o", 40000)], [], "blocked", "one try and one packet"),
 run("window then late", [(1, "accept"), (2, "drop")], [(50, "o", 40000)] + block + [(102000, "o", 40000)], [51], "blocked", "separated by conntrack"),
 run("cannot separate", [(1, "drop"), (2, "accept")], [(300, "t", 40000), (700, "t", 40000)] + block + [(102000, "o", 40000)], [], "inconclusive"),
]
print("ALL PASS" if all(ok) else "SOME FAILED"); sys.exit(0 if all(ok) else 1)
