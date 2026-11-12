#!/usr/bin/env python3
"""Run one disposable Kata pod. Agent and suite validation never receive solution files. Hidden validation's init
container receives only hidden.diff; its test container receives no diffs. Repro fixed receives fix.diff.
Each validation repetition is orchestrated by cases/validate.py.
Post-collection hardening; existing records are unchanged.
usage: pod.py <exec|agent> <case_id> <pod_name> <deadline_s> [--patch FILE] [--env K=V ...] -- <command...>
"""
import copy, json, os, subprocess, sys, time


def build_spec(role, cid, name, deadline, cmd, meta, patch=None, extra_env=(), secret_meta=None):
    if role not in ("exec", "agent"): raise ValueError("unknown pod role")
    ns = "ci-exec" if role == "exec" else "ci-agent"
    CASE = f"/srv/ci/cases/{cid}"
    env = {"CASE_ID": cid, "HOME": "/tmp", "GOMODCACHE": f"{CASE}/gomod", "GOPROXY": "off", "GOSUMDB": "off", "GOFLAGS": "-mod=mod",
           "GOTOOLCHAIN": "auto", "GOCACHE": "/tmp/gocache", "GOPATH": "/tmp/gopath", "GOTELEMETRY": "off",
           "PATH": f"{CASE}/venv/bin:/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
           "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_INDEX": "1"}
    if meta["language"] == "Python": env["VIRTUAL_ENV"] = f"{CASE}/venv"
    for kv in extra_env: k, v = kv.split("=", 1); env[k] = v
    vols = [{"name": "case", "hostPath": {"path": CASE, "type": "Directory"}},
            {"name": "uv", "hostPath": {"path": f"{CASE}/uv", "type": "Directory"}},
            {"name": "repo", "emptyDir": {"sizeLimit": "8Gi"}}, {"name": "tmp", "emptyDir": {"sizeLimit": "8Gi"}},
            {"name": "code", "configMap": {"name": "ci-code"}}]
    mounts = [{"name": "case", "mountPath": CASE, "readOnly": True}, {"name": "uv", "mountPath": "/srv/ci/uv", "readOnly": True},
              {"name": "repo", "mountPath": f"{CASE}/repo"}, {"name": "tmp", "mountPath": "/tmp"}, {"name": "code", "mountPath": "/code", "readOnly": True}]
    # Mount only the inputs this invocation needs. Validation never receives the maintainer's fix or secret directory.
    if role == "exec":
        try: action = cmd[cmd.index("/code/executor.py") + 1:]
        except ValueError: raise ValueError("executor pods require an explicit executor action")
        if not action: raise ValueError("missing executor action")
        fixed = action[:2] == ["repro", "fixed"]
        hidden = (action[:2] == ["validate", "hidden"] or
                  (action[:2] == ["repro", "hidden-broken"] and bool((secret_meta or {}).get("hidden_cmd"))) or
                  (action[0] == "run" and len(action) > 1 and action[1] == "1") or
                  (fixed and bool((secret_meta or {}).get("hidden_cmd"))))
        if action[0] == "validate" and action[1:] not in (["suite"], ["hidden"]):
            raise ValueError("validate requires suite or hidden; use cases/validate.py to aggregate repetitions")
        if fixed or hidden or (action[0] == "run" and action[-1] == "HIDDEN"):
            env["HIDDEN_COMMAND"] = (secret_meta or {}).get("hidden_cmd", "")
        for filename, needed in (("fix.diff", fixed), ("hidden.diff", hidden)):
            if needed:
                key = filename.replace(".", "-")
                vols.append({"name": key, "hostPath": {"path": f"/srv/ci/secret/{cid}/{filename}", "type": "File"}})
                mounts.append({"name": key, "mountPath": f"/in/{filename}", "readOnly": True})
        # Only executor controls/hidden tests receive dependencies prepared from the fixed tree.
        if meta["language"] == "Go" and (fixed or hidden):
            vols.append({"name": "fixed-gomod", "hostPath": {"path": f"/srv/ci/secret/{cid}/gomod", "type": "Directory"}})
            mounts.append({"name": "fixed-gomod", "mountPath": f"{CASE}/gomod", "readOnly": True})
    if patch:
        vols.append({"name": "patch", "configMap": {"name": f"{name}-patch"}})
        mounts.append({"name": "patch", "mountPath": "/in/patch.diff", "subPath": "patch.diff", "readOnly": True})
    spec = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": {"app": "agent" if role == "agent" else "executor", "case": cid[:63]}},
            "spec": {"runtimeClassName": "kata-qemu", "serviceAccountName": "runner", "automountServiceAccountToken": False,
                     "restartPolicy": "Never", "activeDeadlineSeconds": deadline, "enableServiceLinks": False,
                     "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                     "containers": [{"name": "c", "image": "aip-ci-box:1", "imagePullPolicy": "Never", "command": cmd,
                                     "env": [{"name": k, "value": v} for k, v in env.items()],
                                     "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                                     "resources": {"requests": {"cpu": "2", "memory": "4Gi"}, "limits": {"cpu": "3", "memory": "8Gi"}}, "volumeMounts": mounts}],
                     "volumes": vols}}
    if role == "exec" and action[0] == "validate":
        # The init container only copies files and applies patches; it never imports or executes case code.
        # The test container sees the prepared tree, but none of the input diffs or private metadata.
        container = spec["spec"]["containers"][0]
        init = copy.deepcopy(container)
        init["name"] = "prepare"
        init["command"] = ["validate-prepare" if a == "validate" else a for a in cmd]
        container["command"] = ["validate-run" if a == "validate" else a for a in cmd]
        container["volumeMounts"] = [m for m in mounts if not m["mountPath"].startswith("/in/")]
        vols.append({"name": "prepared", "emptyDir": {}})
        init["volumeMounts"].append({"name": "prepared", "mountPath": "/validation"})
        container["volumeMounts"].append({"name": "prepared", "mountPath": "/validation", "readOnly": True})
        spec["spec"]["initContainers"] = [init]
    return spec


def main():
    role, cid, name, deadline = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    rest = sys.argv[5:]; cmd = rest[rest.index("--") + 1:]; opts = rest[:rest.index("--")]
    patch = opts[opts.index("--patch") + 1] if "--patch" in opts else None
    extra_env = [o for i, o in enumerate(opts) if i > 0 and opts[i - 1] == "--env"]
    ns = "ci-exec" if role == "exec" else "ci-agent"
    meta = json.load(open(f"/srv/ci/cases/{cid}/meta.json"))
    secret_meta = json.load(open(f"/srv/ci/secret/{cid}/meta.json")) if role == "exec" else None
    os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    kc = lambda *a, **k: subprocess.run(["kubectl", "-n", ns, *a], capture_output=True, text=True, **k)
    spec = build_spec(role, cid, name, deadline, cmd, meta, patch, extra_env, secret_meta)
    if patch:
        kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")
        result = kc("create", "configmap", f"{name}-patch", f"--from-file=patch.diff={patch}")
        if result.returncode: sys.exit(result.stderr)
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
    # Only the final record of each kind belongs to the harness, not an earlier line printed by a command.
    for tag in ("EXECUTOR ", "RESULT "):
        lines = [line for line in logs.splitlines() if line.startswith(tag)]
        if lines: print(lines[-1])
    print("POD " + json.dumps({"pod": name, "phase": phase, "wall_s": round(time.time() - t0, 1)}))
    kc("delete", "pod", name, "--wait=false")
    if patch: kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")

if __name__ == "__main__":
    main()
