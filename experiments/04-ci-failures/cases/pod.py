#!/usr/bin/env python3
"""Run one disposable Kata pod. Agent and suite validation never receive solution files. Hidden validation's init
container receives only hidden.diff; its test container receives no diffs. Repro fixed and fixed-agent-cache receive
fix.diff; only repro fixed receives the fixed-tree module cache.
Each validation repetition is orchestrated by cases/validate.py.
Post-collection hardening; existing records are unchanged.
usage: pod.py <exec|agent> <case_id> <pod_name> <deadline_s> [--patch FILE] [--env K=V ...] -- <command...>
"""
import copy, json, os, subprocess, sys, time

# Network gate (2026-11-13, after the collection; results/network-2026-11-13). The cluster's policy controller writes a new
# pod's rules some tenths of a second AFTER the pod's network works, so the first process of a pod can reach what the
# namespace's NetworkPolicy forbids. This init container runs before any case code, with no volume and no secret: it
# tries the forbidden canaries until NONE of them has connected in NETGATE_ROUNDS consecutive rounds spanning at least
# NETGATE_SPAN seconds, then (agent pods) waits until the gateway's model port answers. If that does not happen within
# NETGATE_DEADLINE seconds it exits 1 and the pod fails: an infrastructure error, not a result. It proves the rules were
# in force when it looked; it cannot prevent a later lapse of enforcement. NETGATE=0 in the runner's environment builds
# the pod without it (used only to measure the difference).
NETGATE_CODE = r"""
import json, os, socket, sys, threading, time
C = json.loads(os.environ["NETGATE_CONFIG"]); t0 = time.monotonic(); host = os.environ.get("NETGATE_HOST_IP", "")
fix = lambda hp: (host if hp[0] == "$HOST" else hp[0], int(hp[1]))
forbidden = [fix(x) for x in C["forbidden"] if fix(x)[0]]; required = [fix(x) for x in C["required"]]
def tcp(hp, res):
    s = socket.socket(); s.settimeout(C["connect_timeout"])
    try: s.connect(hp); res.append(hp)
    except OSError: pass
    finally: s.close()
def reachable(targets):
    res = []; th = [threading.Thread(target=tcp, args=(hp, res)) for hp in targets]
    [t.start() for t in th]; [t.join() for t in th]; return res
def done(ok, why, **kw):
    print("NETGATE " + json.dumps({"ok": ok, "why": why, "waited_s": round(time.monotonic() - t0, 2), **kw}), flush=True); sys.exit(0 if ok else 1)
rounds = 0; streak = 0; since = None; seen = {}
while True:
    now = time.monotonic() - t0
    if now > C["deadline"]: done(False, "a forbidden destination still answers", rounds=rounds, reachable=seen)
    rounds += 1; hit = reachable(forbidden)
    if hit:
        streak = 0; since = None
        for h, p in hit: seen[f"{h}:{p}"] = seen.get(f"{h}:{p}", 0) + 1
    else:
        streak += 1; since = now if since is None else since
        if streak >= C["rounds"] and now - since >= C["span"]: break
    time.sleep(C["interval"])
while required and len(reachable(required)) < len(required):
    if time.monotonic() - t0 > C["deadline"]: done(False, "a required destination does not answer", rounds=rounds, reachable=seen)
    time.sleep(C["interval"])
done(True, "policy in force", rounds=rounds, reachable_before=seen)
"""

def netgate_container(image, security_context, forbidden, required=()):
    """forbidden/required: (host, port) pairs; host "$HOST" is the node's address (status.hostIP)."""
    cfg = {"forbidden": [list(x) for x in forbidden], "required": [list(x) for x in required],
           "rounds": int(os.environ.get("NETGATE_ROUNDS", "8")), "span": float(os.environ.get("NETGATE_SPAN", "2.0")),
           "interval": float(os.environ.get("NETGATE_INTERVAL", "0.25")), "connect_timeout": float(os.environ.get("NETGATE_CONNECT_TIMEOUT", "0.5")),
           "deadline": float(os.environ.get("NETGATE_DEADLINE", "60"))}
    return {"name": "netgate", "image": image, "imagePullPolicy": "Never", "command": ["python3", "-u", "-c", NETGATE_CODE],
            "env": [{"name": "NETGATE_CONFIG", "value": json.dumps(cfg)},
                    {"name": "NETGATE_HOST_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.hostIP"}}}],
            "securityContext": copy.deepcopy(security_context),
            "resources": {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "1", "memory": "256Mi"}}, "volumeMounts": []}

def netgate_enabled(): return os.environ.get("NETGATE", "1") != "0"
API_CLUSTER_IP = os.environ.get("NETGATE_API", "10.43.0.1:443")           # k3s default; the first address of the service range
PUBLIC_CANARY = os.environ.get("NETGATE_PUBLIC", "1.1.1.1:443")
# metadata endpoint, the node's kubelet port, the Kubernetes API Service: forbidden in every case namespace
PRIVATE_CANARIES = [("169.254.169.254", 80), ("$HOST", 10250), tuple(API_CLUSTER_IP.rsplit(":", 1))]


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
        fixed_cache = action[:2] == ["repro", "fixed"]
        fixed = fixed_cache or action[:2] == ["repro", "fixed-agent-cache"]   # same inputs, the agent's dependency cache
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
        # Agent validation uses the broken-tree cache in BOTH phases. Fixed dependencies are for repro fixed only;
        # "repro fixed-agent-cache" checks that the maintainer's fix also passes without them.
        if meta["language"] == "Go" and fixed_cache:
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
    if netgate_enabled():
        # After validate-prepare (which runs no case code and stays first), immediately before the container that does.
        gw = env.get("GATEWAY_URL", "http://10.43.210.10:8080").split("//", 1)[-1].split("/", 1)[0]
        gate = netgate_container("aip-ci-box:1", spec["spec"]["containers"][0]["securityContext"],
                                 [tuple(PUBLIC_CANARY.rsplit(":", 1))] + PRIVATE_CANARIES,
                                 [tuple(gw.rsplit(":", 1))] if role == "agent" else ())
        spec["spec"].setdefault("initContainers", []).append(gate)
    return spec


def main():
    role, cid, name, deadline = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    rest = sys.argv[5:]; cmd = rest[rest.index("--") + 1:]; opts = rest[:rest.index("--")]
    patch = opts[opts.index("--patch") + 1] if "--patch" in opts else None
    extra_env = [o for i, o in enumerate(opts) if i > 0 and opts[i - 1] == "--env"]
    if role == "agent": extra_env.append("RUN_TOKEN=" + os.environ.pop("RUN_TOKEN"))  # not exposed in CLI arguments
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
    gate = [line for line in kc("logs", name, "-c", "netgate").stdout.splitlines() if line.startswith("NETGATE ")] if netgate_enabled() else []
    gate_failed = netgate_enabled() and not (gate and json.loads(gate[-1][8:]).get("ok"))
    # Only the final record of each kind belongs to the harness, not an earlier line printed by a command.
    for tag in ("EXECUTOR ", "RESULT "):
        lines = [line for line in logs.splitlines() if line.startswith(tag)]
        if lines: print(lines[-1])
    # A failed gate is an infrastructure error: the main container never started, so there is no EXECUTOR/RESULT line.
    print("POD " + json.dumps({"pod": name, "phase": phase, "wall_s": round(time.time() - t0, 1),
                               **({"infra_error": "netgate: " + (gate[-1][8:] if gate else "no result")} if gate_failed else {})}))
    kc("delete", "pod", name, "--wait=false")
    if patch: kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")

if __name__ == "__main__":
    main()
