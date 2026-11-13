#!/usr/bin/env python3
"""Network probe of 2026-11-13, runs INSIDE a probe pod. One thread per target opens a TCP connection every
NETWATCH_INTERVAL seconds for NETWATCH_SECONDS and logs EVERY attempt with wall-clock time:
    A <epoch_ms> <target> <result> <duration_ms> <source_port> [st=<tcp state> peer=<0|1> soerr=<n>]
(the bracketed fields exist from version 2 of this file, 09:02Z, only on tries where connect() returned without an error:
the kernel's TCP state of the socket (1 = ESTABLISHED, 7 = CLOSE), whether getpeername() worked, and SO_ERROR.
netwatch-v1.py is the version the eight steady pods started at 08:51Z ran.)
NETWATCH_RAW=1 (version 3, 09:15Z): every try is made with the separate system calls CPython's connect() uses on a socket
with a timeout (non-blocking connect, poll for POLLOUT|POLLERR, getsockopt SO_ERROR) and logs each result:
rc = errno of connect(2), revents = what poll returned, soerr_first = the first SO_ERROR (0 is what CPython takes as
"connected"), then st / peer / soerr as above, read immediately afterwards.
result: o = connected, r = refused (errno 111), t = timed out, e<errno> = other error. No data is sent or read.
The connect timeout is short (NETWATCH_TIMEOUT, 0.2 s): the policy controller rejects with an ICMP message, the node
rate-limits those messages, so most blocked tries end as a timeout; with a 1 s timeout the probe would make ~1 try/s.
The first line (H) carries the pod's address, the process start time and the target table; the last (S) the totals.
Targets come from PROBE_TARGETS (JSON: node_ip, gw_pod_ip, dns_pod_ip). NETWATCH_ALLOWED (comma list of target labels)
names the destinations this pod's policy allows; NETWATCH_SLOW (comma list) are probed once every 2 s only (used for
the public address where the policy allows it, to keep the traffic to a third party small)."""
import json, os, select, socket, sys, threading, time
T0W = time.time(); T0M = time.monotonic()
T = json.loads(os.environ.get("PROBE_TARGETS", "{}"))
LIMIT = float(os.environ.get("NETWATCH_SECONDS", "16")); INTERVAL = float(os.environ.get("NETWATCH_INTERVAL", "0.1"))
TIMEOUT = float(os.environ.get("NETWATCH_TIMEOUT", "0.2")); RAW = os.environ.get("NETWATCH_RAW", "") == "1"
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
    while RAW:   # version 3: the same try with the system calls made one by one, as CPython's socket.connect() does them
        if time.monotonic() - T0M >= LIMIT: return
        c = socket.socket(); c.setblocking(False); w = time.time(); m = time.monotonic()
        rc = c.connect_ex((host, port))                       # connect(2) on a non-blocking socket: errno, 115 = EINPROGRESS
        p = select.poll(); p.register(c, select.POLLOUT | select.POLLERR); ev = p.poll(TIMEOUT * 1000)
        d = (time.monotonic() - m) * 1000; rev = ev[0][1] if ev else 0
        e1 = c.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) if ev else -1      # what CPython reads to decide success (0) or failure
        st = c.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 1)[0]
        try: c.getpeername(); peer = 1
        except OSError: peer = 0
        e2 = c.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        try: sp = c.getsockname()[1]
        except OSError: sp = 0
        c.close(); s["tries"] += 1
        r = "t" if not ev else ("o" if e1 == 0 else ("r" if e1 == 111 else f"e{e1}")); s[r[0]] += 1
        emit(f"A {int(w * 1000)} {label} {r} {d:.0f} {sp} st={st} peer={peer} soerr={e2} rc={rc} revents={rev:#x} soerr_first={e1}")
        n += 1; nxt = n * period - (time.monotonic() - T0M)
        if nxt > 0: time.sleep(nxt)
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
        extra = ""
        if r == "o":   # v2 (09:02Z): what the socket looks like right after connect() returned without an error
            try: st = c.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 1)[0]       # tcpi_state: 1 = ESTABLISHED, 2 = SYN_SENT, 7 = CLOSE
            except OSError: st = -1
            try: c.getpeername(); peer = 1
            except OSError: peer = 0
            try: soerr = c.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            except OSError: soerr = -1
            extra = f" st={st} peer={peer} soerr={soerr}"
        c.close()
        rel = int((m - T0M) * 1000); s["tries"] += 1; s[r[0]] += 1
        if r == "o":
            s["last_open_ms"] = rel
            if s["first_open_ms"] is None: s["first_open_ms"] = rel
        elif s["first_blocked_ms"] is None: s["first_blocked_ms"] = rel
        if rel > 5000:
            s["tries_after_5s"] += 1; s["open_after_5s"] += r == "o"
        emit(f"A {int(w * 1000)} {label} {r} {d:.0f} {sp}{extra}")
        n += 1; nxt = n * period - (time.monotonic() - T0M)
        if nxt > 0: time.sleep(nxt)
emit("H " + json.dumps({"role": os.environ.get("PROBE_ROLE", ""), "runtime": os.environ.get("PROBE_RUNTIME", ""), "pod": socket.gethostname(), "pod_ip": my_ip(),
                        "probe_version": 3 if RAW else 2, "t0_epoch_ms": int(T0W * 1000), "kernel": os.uname().release, "uid": os.getuid(), "status": status(), "seconds": LIMIT, "interval": INTERVAL,
                        "timeout": TIMEOUT, "allowed": sorted(ALLOWED), "slow": sorted(SLOW), "targets": {l: [f"{h}:{p}", k] for l, h, p, k in TARGETS}}))
threads = [threading.Thread(target=watch, args=t, daemon=True) for t in TARGETS]
[t.start() for t in threads]; [t.join() for t in threads]
emit("S " + json.dumps({"pod": socket.gethostname(), "pod_ip": my_ip(), "end_epoch_ms": int(time.time() * 1000), "targets": summary}))
