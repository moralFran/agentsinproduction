#!/usr/bin/env python3
"""Runs ON aip-ci-01. Starts one throw-away Kata pod for a case, waits for it, returns its log lines that start with a
marker, and deletes it. Roles:
  exec  -> namespace ci-exec (no network), mounts the maintainer's fix/hidden tests (/in/secret) and an optional patch
  agent -> namespace ci-agent (gateway only), NEVER mounts /srv/ci/secret
Both: the case dir read-only at its prepared path, an empty writable dir at <case>/repo, uid 1000, no capabilities,
no service-account token, a hard deadline from Kubernetes.
usage: pod.py <exec|agent> <case_id> <pod_name> <deadline_s> [--patch FILE] [--env K=V ...] -- <command...>"""
import json, os, subprocess, sys, time

role, cid, name, deadline = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
rest = sys.argv[5:]; cmd = rest[rest.index("--") + 1:]; opts = rest[:rest.index("--")]
patch = opts[opts.index("--patch") + 1] if "--patch" in opts else None
extra_env = [o for i, o in enumerate(opts) if i > 0 and opts[i - 1] == "--env"]
ns = "ci-exec" if role == "exec" else "ci-agent"
CASE = f"/srv/ci/cases/{cid}"; meta = json.load(open(f"{CASE}/meta.json"))
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
kc = lambda *a, **k: subprocess.run(["kubectl", "-n", ns, *a], capture_output=True, text=True, **k)

env = {"CASE_ID": cid, "HOME": "/tmp", "GOMODCACHE": f"{CASE}/gomod", "GOPROXY": "off", "GOSUMDB": "off", "GOFLAGS": "-mod=mod",
       "GOTOOLCHAIN": "auto", "GOCACHE": "/tmp/gocache", "GOPATH": "/tmp/gopath", "GOTELEMETRY": "off",
       "PATH": f"{CASE}/venv/bin:/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
       "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_INDEX": "1"}
if meta["language"] == "Python": env["VIRTUAL_ENV"] = f"{CASE}/venv"
for kv in extra_env: k, v = kv.split("=", 1); env[k] = v
vols = [{"name": "case", "hostPath": {"path": CASE, "type": "Directory"}},
        {"name": "uv", "hostPath": {"path": "/srv/ci/uv", "type": "DirectoryOrCreate"}},
        {"name": "repo", "emptyDir": {"sizeLimit": "8Gi"}}, {"name": "tmp", "emptyDir": {"sizeLimit": "8Gi"}},
        {"name": "code", "configMap": {"name": "ci-code"}}]
mounts = [{"name": "case", "mountPath": CASE, "readOnly": True}, {"name": "uv", "mountPath": "/srv/ci/uv", "readOnly": True},
          {"name": "repo", "mountPath": f"{CASE}/repo"}, {"name": "tmp", "mountPath": "/tmp"}, {"name": "code", "mountPath": "/code", "readOnly": True}]
if role == "exec":
    vols.append({"name": "secret", "hostPath": {"path": f"/srv/ci/secret/{cid}", "type": "Directory"}})
    mounts.append({"name": "secret", "mountPath": "/in/secret", "readOnly": True})
if patch:
    kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")
    r = kc("create", "configmap", f"{name}-patch", f"--from-file=patch.diff={patch}")
    if r.returncode: sys.exit(r.stderr)
    vols.append({"name": "patch", "configMap": {"name": f"{name}-patch"}})
    mounts.append({"name": "patch", "mountPath": "/in/patch.diff", "subPath": "patch.diff", "readOnly": True})
spec = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": {"app": "agent" if role == "agent" else "executor", "case": cid[:63]}},
        "spec": {"runtimeClassName": "kata-qemu", "serviceAccountName": "runner", "automountServiceAccountToken": False,
                 "restartPolicy": "Never", "activeDeadlineSeconds": deadline, "enableServiceLinks": False,
                 "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000},
                 "containers": [{"name": "c", "image": "aip-ci-box:1", "imagePullPolicy": "Never", "command": cmd,
                                 "env": [{"name": k, "value": v} for k, v in env.items()],
                                 "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                                 "resources": {"requests": {"cpu": "2", "memory": "4Gi"}, "limits": {"cpu": "3", "memory": "8Gi"}}, "volumeMounts": mounts}],
                 "volumes": vols}}
kc("delete", "pod", name, "--ignore-not-found", "--wait=true")
r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), capture_output=True, text=True)
if r.returncode: sys.exit(r.stderr)
t0 = time.time(); phase = ""
while time.time() - t0 < deadline + 120:
    phase = kc("get", "pod", name, "-o", "jsonpath={.status.phase}/{.status.reason}").stdout
    if phase.split("/")[0] in ("Succeeded", "Failed"): break
    time.sleep(2)
logs = kc("logs", name).stdout
open(f"/srv/ci/logs/{name}.log", "w").write(logs) if os.path.isdir("/srv/ci/logs") else None
for line in logs.splitlines():
    if line.startswith(("EXECUTOR ", "RESULT ")): print(line)
print("POD " + json.dumps({"pod": name, "phase": phase, "wall_s": round(time.time() - t0, 1)}))
kc("delete", "pod", name, "--wait=false")
if patch: kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")
