#!/usr/bin/env python3
"""Integration probe (2026-11-12), runs INSIDE a probe pod. Measures WHEN the NetworkPolicy starts to apply to a new pod:
from the first instruction of the container's process, it tries a TCP connection to each target every ~0.3 s for
NETTIME_SECONDS and prints each change of state with the time since the process started. No data is sent or read."""
import json, os, socket, time
T0 = time.monotonic(); T = json.loads(os.environ.get("PROBE_TARGETS", "{}")); LIMIT = float(os.environ.get("NETTIME_SECONDS", "40"))
targets = [("public 1.1.1.1:443", "1.1.1.1", 443), ("metadata 169.254.169.254:80", "169.254.169.254", 80),
           ("node ssh", T.get("node_ip"), 22), ("kubernetes api clusterip", "10.43.0.1", 443),
           ("gateway model port", "10.43.210.10", 8080), ("gateway admin port", "10.43.210.10", 8081), ("dns pod tcp 53", T.get("dns_pod_ip"), 53)]
def tcp(host, port):
    s = socket.socket(); s.settimeout(1.0)
    try: s.connect((host, port)); return "open"
    except socket.timeout: return "timeout"
    except OSError as e: return "refused" if e.errno == 111 else f"error {e.errno}"
    finally: s.close()
state = {}; summary = {label: {"open": 0, "blocked": 0, "last_open_s": None, "first_blocked_s": None} for label, h, _ in targets if h}
print("NETTIME " + json.dumps({"event": "start", "role": os.environ.get("PROBE_ROLE", ""), "uid": os.getuid()}), flush=True)
while time.monotonic() - T0 < LIMIT:
    for label, host, port in targets:
        if not host: continue
        t = round(time.monotonic() - T0, 2); r = tcp(host, port); s = summary[label]
        if r == "open": s["open"] += 1; s["last_open_s"] = t
        else:
            s["blocked"] += 1
            if s["first_blocked_s"] is None: s["first_blocked_s"] = t
        if state.get(label) != r:
            state[label] = r; print("NETTIME " + json.dumps({"t_s": t, "target": label, "result": r}), flush=True)
    time.sleep(0.3)
print("NETTIME " + json.dumps({"event": "summary", "seconds": LIMIT, "targets": summary}), flush=True)
