#!/usr/bin/env python3
"""Network probe of 2026-11-13, runs INSIDE a probe pod. One thread per target opens a TCP connection every
NETWATCH_INTERVAL seconds for NETWATCH_SECONDS and logs EVERY attempt with wall-clock time:
    A <epoch_ms> <target> <result> <duration_ms> <source_port>
result: o = connected, r = refused (errno 111), t = timed out, e<errno> = other error. No data is sent or read.
The connect timeout is short (NETWATCH_TIMEOUT, 0.2 s): the policy controller rejects with an ICMP message, the node
rate-limits those messages, so most blocked tries end as a timeout; with a 1 s timeout the probe would make ~1 try/s.
The first line (H) carries the pod's address, the process start time and the target table; the last (S) the totals.
Targets come from PROBE_TARGETS (JSON: node_ip, gw_pod_ip, dns_pod_ip). NETWATCH_ALLOWED (comma list of target labels)
names the destinations this pod's policy allows; NETWATCH_SLOW (comma list) are probed once every 2 s only (used for
the public address where the policy allows it, to keep the traffic to a third party small)."""
import json, os, socket, sys, threading, time
T0W = time.time(); T0M = time.monotonic()
T = json.loads(os.environ.get("PROBE_TARGETS", "{}"))
LIMIT = float(os.environ.get("NETWATCH_SECONDS", "16")); INTERVAL = float(os.environ.get("NETWATCH_INTERVAL", "0.1"))
TIMEOUT = float(os.environ.get("NETWATCH_TIMEOUT", "0.2"))
ALLOWED = set(filter(None, os.environ.get("NETWATCH_ALLOWED", "").split(","))); SLOW = set(filter(None, os.environ.get("NETWATCH_SLOW", "").split(",")))
TARGETS = [("pub", "1.1.1.1", 443, "external"), ("meta", "169.254.169.254", 80, "external"),
           ("node22", T.get("node_ip"), 22, "external"), ("node6443", T.get("node_ip"), 6443, "external"),
           ("api", "10.43.0.1", 443, "internal"), ("gwm", "10.43.210.10", 8080, "internal"), ("gwa", "10.43.210.10", 8081, "internal"),
           ("gwpm", T.get("gw_pod_ip"), 8080, "internal"), ("gwpa", T.get("gw_pod_ip"), 8081, "internal"), ("dns", T.get("dns_pod_ip"), 53, "internal")]
TARGETS = [t for t in TARGETS if t[1]]
only = set(filter(None, os.environ.get("NETWATCH_ONLY", "").split(",")))
if only: TARGETS = [t for t in TARGETS if t[0] in only]
lock = threading.Lock(); out = sys.stdout
def emit(line):
    with lock: out.write(line + "\n"); out.flush()
def my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.43.0.1", 9)); ip = s.getsockname()[0]; s.close(); return ip
    except OSError: return ""
def status():
    try: return {l.split(":")[0]: l.split(":", 1)[1].strip() for l in open("/proc/self/status") if l.split(":")[0] in ("Seccomp", "Seccomp_filters", "NoNewPrivs")}
    except OSError: return {}
summary = {}
def watch(label, host, port, kind):
    s = summary[label] = {"tries": 0, "o": 0, "r": 0, "t": 0, "e": 0, "first_open_ms": None, "last_open_ms": None, "first_blocked_ms": None,
                          "open_after_5s": 0, "tries_after_5s": 0}
    period = 2.0 if label in SLOW else INTERVAL; n = 0
    while True:
        now = time.monotonic() - T0M
        if now >= LIMIT: break
        c = socket.socket(); c.settimeout(TIMEOUT); w = time.time(); m = time.monotonic()
        try: c.connect((host, port)); r = "o"
        except socket.timeout: r = "t"
        except OSError as e: r = "r" if e.errno == 111 else f"e{e.errno}"
        d = (time.monotonic() - m) * 1000
        try: sp = c.getsockname()[1]
        except OSError: sp = 0
        c.close()
        rel = int((m - T0M) * 1000); s["tries"] += 1; s[r[0]] += 1
        if r == "o":
            s["last_open_ms"] = rel
            if s["first_open_ms"] is None: s["first_open_ms"] = rel
        elif s["first_blocked_ms"] is None: s["first_blocked_ms"] = rel
        if rel > 5000:
            s["tries_after_5s"] += 1; s["open_after_5s"] += r == "o"
        emit(f"A {int(w * 1000)} {label} {r} {d:.0f} {sp}")
        n += 1; nxt = n * period - (time.monotonic() - T0M)
        if nxt > 0: time.sleep(nxt)
emit("H " + json.dumps({"role": os.environ.get("PROBE_ROLE", ""), "runtime": os.environ.get("PROBE_RUNTIME", ""), "pod": socket.gethostname(), "pod_ip": my_ip(),
                        "t0_epoch_ms": int(T0W * 1000), "kernel": os.uname().release, "uid": os.getuid(), "status": status(), "seconds": LIMIT, "interval": INTERVAL,
                        "timeout": TIMEOUT, "allowed": sorted(ALLOWED), "slow": sorted(SLOW), "targets": {l: [f"{h}:{p}", k] for l, h, p, k in TARGETS}}))
threads = [threading.Thread(target=watch, args=t, daemon=True) for t in TARGETS]
[t.start() for t in threads]; [t.join() for t in threads]
emit("S " + json.dumps({"pod": socket.gethostname(), "pod_ip": my_ip(), "end_epoch_ms": int(time.time() * 1000), "targets": summary}))
