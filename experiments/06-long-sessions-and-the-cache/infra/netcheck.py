#!/usr/bin/env python3
"""Runs ON aip-ctx-01. One throw-away Kata pod in a case namespace (default ci-agent), built with the harness's own
network gate. No gateway is required (phase 2 has none). After the gate passes, the main container tries DNS, the public
internet (TCP 443/80, three addresses), the metadata endpoint, the node (ssh, kubelet), the Kubernetes API and the
gateway's service address, and prints what answered. Expected: nothing answers. Mounts nothing; no app code.
usage: netcheck.py [ci-agent|ci-exec]"""
import importlib.util, json, os, pathlib, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pod", HERE.parent / "cases" / "pod.py"); pod = importlib.util.module_from_spec(spec); spec.loader.exec_module(pod)
ns = sys.argv[1] if len(sys.argv) > 1 else "ci-agent"; name = f"netcheck-{int(time.time()) % 100000}"
PROBE = r'''
import json, os, socket, subprocess
host = os.environ.get("HOST_IP", "")
targets = [("1.1.1.1", 443), ("8.8.8.8", 443), ("142.250.190.14", 80), ("169.254.169.254", 80), (host, 22), (host, 10250), ("10.43.0.1", 443), ("10.43.210.10", 8080), ("10.43.210.10", 8081), ("10.43.0.10", 53)]
out = {}
for h, p in targets:
    res = []
    for _ in range(3):
        s = socket.socket(); s.settimeout(1.5)
        try: s.connect((h, p)); res.append("CONNECTED")
        except OSError as e: res.append(type(e).__name__)
        finally: s.close()
    out[f"{h}:{p}"] = res
try: out["dns pub.dev"] = socket.gethostbyname("pub.dev")
except OSError as e: out["dns pub.dev"] = "no: " + type(e).__name__
out["default route"] = subprocess.run("cat /proc/net/route | head -3", shell=True, capture_output=True, text=True).stdout.split("\n")[1:2]
out["seccomp"] = [l for l in open("/proc/self/status") if l.startswith("Seccomp")][0].strip()
out["uid"] = os.getuid()
print("NETCHECK " + json.dumps(out))
'''
sec = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
gate = pod.netgate_container(pod.BOX_IMAGE, sec, [tuple(pod.PUBLIC_CANARY.rsplit(":", 1))] + pod.PRIVATE_CANARIES)
spec = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns}, "spec": {
    "runtimeClassName": "kata-qemu", "serviceAccountName": "runner", "automountServiceAccountToken": False, "restartPolicy": "Never",
    "activeDeadlineSeconds": 240, "enableServiceLinks": False,
    "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
    "initContainers": [gate],
    "containers": [{"name": "c", "image": pod.BOX_IMAGE, "imagePullPolicy": "Never", "command": ["python3", "-u", "-c", PROBE],
                    "env": [{"name": "HOST_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.hostIP"}}}], "securityContext": sec,
                    "resources": {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "512Mi"}}}]}}
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
kc = lambda *a: subprocess.run(["kubectl", "-n", ns, *a], capture_output=True, text=True)
r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), capture_output=True, text=True)
if r.returncode: sys.exit(r.stderr)
for _ in range(150):
    phase = kc("get", "pod", name, "-o", "jsonpath={.status.phase}").stdout
    if phase in ("Succeeded", "Failed"): break
    time.sleep(2)
print("namespace:", ns, "| pod phase:", phase)
print(kc("logs", name, "-c", "netgate").stdout.strip()); print(kc("logs", name).stdout.strip())
kc("delete", "pod", name, "--wait=false")
