#!/usr/bin/env python3
"""Capture helper (2026-11-13), runs INSIDE a pod as its first process. Every 0.2 s it tries one TCP connection to each
of four destinations the namespace's NetworkPolicy forbids and prints one row: seconds since this process started and,
per destination, OPEN (the connection was established: TCP state ESTABLISHED), refused (the node's rejection arrived)
or "no answer" (nothing came back within 0.18 s (0.15 s in the first take of c21); the node rate-limits its rejections). No data is sent.
PROBE_CLOCK=1 (capture c26) prints the pod's UTC clock instead of the seconds since start; PROBE_ROUNDS and PROBE_EVERY
set how many rows and how often."""
import os, socket, threading, time
T0 = time.monotonic(); NODE = os.environ.get("NODE_IP", "")
TARGETS = [("1.1.1.1:443", "1.1.1.1", 443), ("metadata", "169.254.169.254", 80), ("node:22", NODE, 22), ("k8s API", "10.43.0.1", 443)]
ROUNDS = int(os.environ.get("PROBE_ROUNDS", "8")); EVERY = float(os.environ.get("PROBE_EVERY", "0.2")); TIMEOUT = 0.18
CLOCK = os.environ.get("PROBE_CLOCK") == "1"
def tcp(host, port, res, i):
    s = socket.socket(); s.settimeout(TIMEOUT)
    try:
        s.connect((host, port))
        res[i] = "OPEN" if s.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 1)[0] == 1 else "refused"
    except socket.timeout: res[i] = "no answer"
    except OSError as e: res[i] = "refused" if e.errno == 111 else f"error {e.errno}"
    finally: s.close()
print(f"{'UTC time' if CLOCK else 'since start':>11}   " + "".join(f"{t[0]:<13}" for t in TARGETS), flush=True)
for n in range(ROUNDS):
    t = time.monotonic() - T0; w = time.time(); res = [""] * len(TARGETS)
    th = [threading.Thread(target=tcp, args=(h, p, res, i)) for i, (_, h, p) in enumerate(TARGETS)]
    [x.start() for x in th]; [x.join() for x in th]
    stamp = time.strftime("%H:%M:%S", time.gmtime(w)) + f".{int(w * 10) % 10}" if CLOCK else f"{t:9.2f} s"
    print(f"{stamp:>11}   " + "".join(f"{r:<13}" for r in res), flush=True)
    time.sleep(max(0, (n + 1) * EVERY - (time.monotonic() - T0)))
