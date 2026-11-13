#!/usr/bin/env python3
"""Capture helper (2026-11-13), runs ON the lab VM. Starts ONE new pod in ci-exec built by the harness's own spec builder
(cases/pod.py build_spec, executor role: same namespace, service account, user, security context, runtime class), with
only the main container's command replaced: "probe" runs capture/probe.py from the pod's first instant, "idle" sleeps
so that `kubectl exec` can look inside. NETGATE=0 in the environment builds the pod without the network gate init
container (pod.py's own switch). "runc" removes runtimeClassName (default runtime, same namespace and policy).
"watch" (capture c26) starts the probe in the namespace cap-open, which has NO NetworkPolicy until the capture applies one:
no gate there (it could never pass), 15 s of rows with the pod's clock; it returns when the pod is running.
Prints one line when the pod has finished (probe) or is running (idle, watch).  usage: newpod.py probe|idle|watch kata|runc <name>"""
import json, os, subprocess, sys, time
mode, rt, name = sys.argv[1:4]; NS = "cap-open" if mode == "watch" else "ci-exec"
if mode == "watch": os.environ["NETGATE"] = "0"
RUN = os.path.expanduser("~/run"); CID = "gobwas-ws-a567dfd6"; HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUN + "/cases"); os.chdir(RUN); os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
import pod
kc = lambda *a, **k: subprocess.run(["kubectl", "-n", NS, *a], capture_output=True, text=True, **k)
meta = json.load(open(f"/srv/ci/cases/{CID}/meta.json")); secret = json.load(open(f"/srv/ci/secret/{CID}/meta.json"))
spec = pod.build_spec("exec", CID, name, 180, ["python3", "-u", "/code/executor.py", "repro", "broken", "1"], meta, None, (), secret)
c = spec["spec"]["containers"][0]
c["command"] = ["sleep", "150"] if mode == "idle" else ["python3", "-u", "/probe/probe.py"]
spec["metadata"]["namespace"] = NS
if mode == "watch": c["env"] += [{"name": "PROBE_CLOCK", "value": "1"}, {"name": "PROBE_ROUNDS", "value": "60"}, {"name": "PROBE_EVERY", "value": "0.25"}]
c["env"].append({"name": "NODE_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.hostIP"}}})
c["volumeMounts"].append({"name": "probe", "mountPath": "/probe", "readOnly": True})
spec["spec"]["volumes"].append({"name": "probe", "configMap": {"name": "capture-probe"}})
if rt == "runc": del spec["spec"]["runtimeClassName"]
for x in spec["spec"]["containers"] + spec["spec"].get("initContainers", []): x["resources"]["requests"] = {"cpu": "100m", "memory": "256Mi"}
gate = any(x["name"] == "netgate" for x in spec["spec"].get("initContainers", []))
cm = kc("create", "configmap", "capture-probe", f"--from-file={HERE}/probe.py", "-o", "yaml", "--dry-run=client").stdout
subprocess.run(["kubectl", "apply", "-f", "-"], input=cm, text=True, capture_output=True, check=True)
kc("delete", "pod", name, "--ignore-not-found", "--wait=true")
subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), text=True, capture_output=True, check=True)
t0 = time.time(); phase = ""
while time.time() - t0 < 90:
    phase = kc("get", "pod", name, "-o", "jsonpath={.status.phase}").stdout
    if phase in ("Succeeded", "Failed") or (mode != "probe" and phase == "Running"): break
    time.sleep(0.5)
print(f"pod {name}: {phase} | {NS} | {'Kata (kata-qemu)' if rt == 'kata' else 'runc'} | network gate: {'yes' if gate else 'no'}")
