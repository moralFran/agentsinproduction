#!/usr/bin/env python3
"""2026-11-13, runs ON the VM. Records every pod (or NetworkPolicy) event the API server sends, with the wall-clock
time this watcher RECEIVED it (epoch ms): the same stream the policy controller reacts to. One JSON line per event.
usage: podwatch.py pods|networkpolicies <out.jsonl>"""
import json, os, subprocess, sys, time
kind, out = sys.argv[1], open(sys.argv[2], "a", buffering=1)
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
dec = json.JSONDecoder()
def state(cs):
    s = cs.get("state", {}); k = next(iter(s), "")
    return {"name": cs.get("name"), "state": k, **{f: s[k][f] for f in ("startedAt", "finishedAt", "exitCode", "reason") if f in s.get(k, {})}}
while True:
    p = subprocess.Popen(["kubectl", "get", kind, "-A", "--watch", "--output-watch-events", "-o", "json"], stdout=subprocess.PIPE, text=True)
    for chunk in iter(lambda: p.stdout.readline(), ""):      # kubectl prints one compact JSON object per event line
        try: ev = json.loads(chunk)
        except ValueError: continue
        o = ev.get("object", {}); m = o.get("metadata", {}); st = o.get("status", {}); now = int(time.time() * 1000)
        rec = {"t_ms": now, "event": ev.get("type"), "ns": m.get("namespace"), "name": m.get("name"), "uid": m.get("uid"), "rv": m.get("resourceVersion"),
               "created": m.get("creationTimestamp"), "deleting": m.get("deletionTimestamp")}
        if kind == "pods":
            rec.update(phase=st.get("phase"), pod_ip=st.get("podIP"), runtime=o.get("spec", {}).get("runtimeClassName") or "runc", labels=m.get("labels"),
                       init=[state(c) for c in st.get("initContainerStatuses", [])], containers=[state(c) for c in st.get("containerStatuses", [])],
                       conditions={c["type"]: [c["status"], c.get("lastTransitionTime")] for c in st.get("conditions", [])})
        else: rec.update(generation=m.get("generation"))
        out.write(json.dumps(rec) + "\n")
    out.write(json.dumps({"t_ms": int(time.time() * 1000), "event": "WATCH_RESTART"}) + "\n"); time.sleep(1)
