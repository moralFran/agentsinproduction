#!/usr/bin/env python3
"""Integration probe (2026-11-12), runs INSIDE a probe pod. Steady-state check of the NetworkPolicies while other pods
are created and deleted around it: one thread per target tries a TCP connection every ~0.2 s for NETFLAP_SECONDS and
logs every change between reachable and blocked, with the time since the process started. No data is sent or read."""
import json, os, socket, threading, time
T0 = time.monotonic(); T = json.loads(os.environ.get("PROBE_TARGETS", "{}")); LIMIT = float(os.environ.get("NETFLAP_SECONDS", "300"))
targets = [("public 1.1.1.1:443", "1.1.1.1", 443), ("metadata 169.254.169.254:80", "169.254.169.254", 80),
           ("node ssh", T.get("node_ip"), 22), ("kubernetes api clusterip", "10.43.0.1", 443),
           ("gateway model port", "10.43.210.10", 8080), ("gateway admin port", "10.43.210.10", 8081)]
lock = threading.Lock(); summary = {}
def say(obj):
    with lock: print("NETFLAP " + json.dumps(obj), flush=True)
def watch(label, host, port):
    s = summary[label] = {"tries": 0, "open": 0, "blocked": 0, "changes": 0, "open_after_5s": 0, "blocked_after_5s": 0}; last = None
    while time.monotonic() - T0 < LIMIT:
        t = round(time.monotonic() - T0, 2); c = socket.socket(); c.settimeout(0.5)
        try: c.connect((host, port)); r = "open"
        except OSError: r = "blocked"
        finally: c.close()
        s["tries"] += 1; s[r] += 1
        if t > 5: s[r + "_after_5s"] += 1
        if r != last:
            s["changes"] += 1; last = r
            if s["changes"] <= 60: say({"t_s": t, "target": label, "now": r})
        time.sleep(0.2)
say({"event": "start", "role": os.environ.get("PROBE_ROLE", ""), "seconds": LIMIT})
threads = [threading.Thread(target=watch, args=x) for x in targets if x[1]]
[t.start() for t in threads]; [t.join() for t in threads]
say({"event": "summary", "seconds": LIMIT, "targets": summary})
