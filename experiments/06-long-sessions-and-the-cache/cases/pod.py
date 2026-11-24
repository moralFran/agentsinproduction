#!/usr/bin/env python3
"""Run one disposable Kata pod (experiment 05, adapted from experiment 04's pod.py). Agent pods and the test container
of executor pods never receive the owner's fix, an agent patch file or the secret directory: diffs are mounted in the
executor's init container only, which copies and applies files and runs no app code. Each sample of each test job is
its own pod, orchestrated by cases/team_host.py.
usage: pod.py <exec|agent> <case_id> <pod_name> <deadline_s> [--tree baseline|gold|patch] [--patch FILE] [--cpu N] [--memory M]
              [--env K=V ...] -- <command...>
"""
import copy, json, os, re, subprocess, sys, time

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


BOX_IMAGE = os.environ.get("BOX_IMAGE", "aip-team-box:1")
PUB_CACHE = "/srv/ci/deps/pub-cache"          # filled once by the dependency preparation (criteria E6), read-only in every pod
OUT_ROOT = "/srv/ci/out"                      # one writable directory per executor pod, for its result file only
# Working copy and /tmp. In a Kata pod a plain emptyDir is a host directory shared through virtiofs, and the compiler's
# and Jest's many small writes go through it (measured 15/11: the host spent about 45 % of its CPU in system time during
# a Flutter suite). medium=Memory makes them a tmpfs inside the guest; it counts against the pod's memory limit.
# SCRATCH_MEDIUM=disk restores the host-backed directories.
SCRATCH = {"sizeLimit": "8Gi"} if os.environ.get("SCRATCH_MEDIUM") == "disk" else {"medium": "Memory", "sizeLimit": "6Gi"}


LAB_ROOT = os.environ.get("TEAM_ROOT", "/srv/ci")
KATA_BASE_GI = 2.0     # Kata's default_memory: every sandbox VM is sized (memory limit + this)


class cpu_slots:
    """A CPU and memory budget shared by every controller on the VM (reproduction queue, validators, probes).
    CPU: a pod starts only when the CPU limits of the pods already running plus its own fit in /srv/ci/queue.cpus
    (default 8 = the VM's vCPUs).
    Memory: with virtiofs, Kata backs each guest's RAM with a file in the host's /dev/shm, and a guest never gives memory
    back, so every sandbox grows towards (memory limit + 2 GiB). When /dev/shm fills up, a QEMU process dies and its pod
    fails with no output (seen 15/11, 18:28: "qemu-system-x86_64: Unexpected end-of-file"). So the sum of
    (limit + 2 GiB) over running pods must fit in /srv/ci/queue.mem GiB (default 26; /dev/shm is remounted at 28G by
    infra/host-tune.sh). The ledger is /srv/ci/cpu.json under an flock; entries of dead controllers are dropped."""
    LEDGER, LOCK = LAB_ROOT + "/cpu.json", LAB_ROOT + "/cpu.lock"

    def __init__(self, name, cpu, memory="0Gi"):
        self.name, self.cpu, self.mem = name, float(cpu), float(str(memory).replace("Gi", "")) + KATA_BASE_GI

    def _edit(self, fn):
        import fcntl
        with open(self.LOCK, "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try: ledger = json.load(open(self.LEDGER))
            except (OSError, ValueError): ledger = {}
            ledger = {k: v for k, v in ledger.items() if self._alive(v["pid"])}
            out = fn(ledger)
            tmp = str(self.LEDGER) + ".tmp"; open(tmp, "w").write(json.dumps(ledger)); os.replace(tmp, self.LEDGER)
            return out

    @staticmethod
    def _alive(pid):
        try: os.kill(int(pid), 0); return True
        except ProcessLookupError: return False
        except (PermissionError, ValueError, OSError): return True

    @staticmethod
    def _budget(name, default):
        try: return float(open(LAB_ROOT + "/" + name).read().strip())
        except (OSError, ValueError): return default

    def __enter__(self):
        def take(ledger):
            cpus, mem = self._budget("queue.cpus", 8.0), self._budget("queue.mem", 26.0)
            used_c = sum(v["cpu"] for v in ledger.values()); used_m = sum(v.get("mem", 0) for v in ledger.values())
            if (used_c + self.cpu <= cpus and used_m + self.mem <= mem) or not ledger:      # a job larger than the budget still runs, alone
                ledger[self.name] = {"pid": os.getpid(), "cpu": self.cpu, "mem": self.mem, "since": time.time()}; return True
            return False
        while not self._edit(take): time.sleep(3)
        return self

    def __exit__(self, *exc): self._edit(lambda ledger: ledger.pop(self.name, None))


def deps_mounts(cid, meta):
    """Read-only dependency volumes shared by agent and executor pods, each at the same absolute path it has on the VM:
    the pub cache (the generated .dart_tool/package_config.json points there) and the task's node_modules set
    (meta["node_dir"]; the working copy reaches it through two symlinks that come with the overlay). No app code."""
    CASE = f"/srv/ci/cases/{cid}"; vols, mounts = [], []
    if os.path.isdir(PUB_CACHE):
        vols.append({"name": "pubcache", "hostPath": {"path": PUB_CACHE, "type": "Directory"}})
        mounts.append({"name": "pubcache", "mountPath": PUB_CACHE, "readOnly": True})
    host = meta.get("node_dir")
    if host:
        if not re.fullmatch(r"/srv/ci/deps/node/node-[0-9a-f]+", host): raise ValueError("invalid node_modules directory")
        vols.append({"name": "nodedeps", "hostPath": {"path": host, "type": "Directory"}})
        mounts.append({"name": "nodedeps", "mountPath": host, "readOnly": True})
    return vols, mounts


def build_spec(role, cid, name, deadline, cmd, meta, patch=None, extra_env=(), secret_meta=None, tree=None, cpu="3", memory="8Gi", out_dir=None):
    """role "agent": the working copy, the dependencies and the gateway. role "exec": one sample of one test job
    (executor/team.py). tree is "baseline" (snapshot as the agent sees it), "gold" (+ the owner's fix, mounted in the
    init container only) or "patch" (+ an agent patch, checked and applied in the init container only). The test
    container never mounts a diff or the secret directory; its only writable host path is its own result directory."""
    if role not in ("exec", "agent"): raise ValueError("unknown pod role")
    ns = "ci-exec" if role == "exec" else "ci-agent"
    CASE = f"/srv/ci/cases/{cid}"
    # PATH, PUB_CACHE, FIREBASE_EMULATORS_PATH and the telemetry switches come from the image. HOME is the image's own
    # home (holds only the tools' telemetry-off settings); NPM offline so npm/npx never wait for a registry.
    env = {"CASE_ID": cid, "HOME": "/home/agent", "NPM_CONFIG_OFFLINE": "true", "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_INDEX": "1"}
    for kv in extra_env: k, v = kv.split("=", 1); env[k] = v
    vols = [{"name": "case", "hostPath": {"path": CASE, "type": "Directory"}},
            {"name": "repo", "emptyDir": dict(SCRATCH)}, {"name": "tmp", "emptyDir": dict(SCRATCH)},
            {"name": "code", "configMap": {"name": "ci-code"}}]
    mounts = [{"name": "case", "mountPath": CASE, "readOnly": True},
              {"name": "repo", "mountPath": f"{CASE}/repo"}, {"name": "tmp", "mountPath": "/tmp"}, {"name": "code", "mountPath": "/code", "readOnly": True}]
    dv, dm = deps_mounts(cid, meta); vols += dv; mounts += dm
    init_only = []
    if role == "exec":
        if tree not in ("baseline", "gold", "patch"): raise ValueError("executor pods need tree=baseline|gold|patch")
        if tree == "gold":
            vols.append({"name": "fix-diff", "hostPath": {"path": f"/srv/ci/secret/{cid}/fix.diff", "type": "File"}})
            init_only.append({"name": "fix-diff", "mountPath": "/in/fix.diff", "readOnly": True})
        if tree == "patch":
            if not patch: raise ValueError("tree=patch needs --patch")
            vols.append({"name": "patch", "configMap": {"name": f"{name}-patch"}})
            init_only.append({"name": "patch", "mountPath": "/in/patch.diff", "subPath": "patch.diff", "readOnly": True})
    elif patch:
        raise ValueError("agent pods take no patch")
    container = {"name": "c", "image": BOX_IMAGE, "imagePullPolicy": "Never", "command": cmd,
                 "env": [{"name": k, "value": v} for k, v in env.items()],
                 "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                 "resources": {"requests": {"cpu": "1", "memory": "2Gi"}, "limits": {"cpu": str(cpu), "memory": str(memory)}}, "volumeMounts": list(mounts)}
    spec = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": {"app": "agent" if role == "agent" else "executor", "case": cid[:63]}},
            "spec": {"runtimeClassName": "kata-qemu", "serviceAccountName": "runner", "automountServiceAccountToken": False,
                     "restartPolicy": "Never", "activeDeadlineSeconds": deadline, "enableServiceLinks": False,
                     "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                     "containers": [container], "volumes": vols}}
    if role == "exec":
        # The init container only copies files and applies diffs; it never imports or executes app code.
        init = copy.deepcopy(container)
        init["name"] = "prepare"; init["command"] = ["python3", "-u", "/code/team.py", "prepare", tree]
        init["volumeMounts"] += init_only
        vols.append({"name": "prepared", "emptyDir": {}})
        init["volumeMounts"].append({"name": "prepared", "mountPath": "/validation"})
        container["volumeMounts"].append({"name": "prepared", "mountPath": "/validation", "readOnly": True})
        if out_dir:
            if not out_dir.startswith(OUT_ROOT + "/") or ".." in out_dir: raise ValueError("invalid result directory")
            vols.append({"name": "out", "hostPath": {"path": out_dir, "type": "Directory"}})
            container["volumeMounts"].append({"name": "out", "mountPath": "/out"})
        spec["spec"]["initContainers"] = [init]
    if netgate_enabled():
        # After prepare (which runs no app code and stays first), immediately before the container that does.
        gw = env.get("GATEWAY_URL", "http://10.43.210.10:8080").split("//", 1)[-1].split("/", 1)[0]
        gate = netgate_container(BOX_IMAGE, container["securityContext"],
                                 [tuple(PUBLIC_CANARY.rsplit(":", 1))] + PRIVATE_CANARIES,
                                 [tuple(gw.rsplit(":", 1))] if role == "agent" and os.environ.get("NETGATE_REQUIRE_GATEWAY", "1") != "0" else ())
        spec["spec"].setdefault("initContainers", []).append(gate)
    return spec


def run_pod(spec, patch=None, log_dir="/srv/ci/logs"):
    """Creates the pod, waits for it, returns (logs, pod record). Deletes the pod and its patch ConfigMap."""
    name, ns = spec["metadata"]["name"], spec["metadata"]["namespace"]; deadline = spec["spec"]["activeDeadlineSeconds"]
    os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    kc = lambda *a, **k: subprocess.run(["kubectl", "-n", ns, *a], capture_output=True, text=True, **k)
    if patch:
        kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")
        result = kc("create", "configmap", f"{name}-patch", f"--from-file=patch.diff={patch}")
        if result.returncode: raise RuntimeError(result.stderr)
    kc("delete", "pod", name, "--ignore-not-found", "--wait=true")
    r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)
    t0 = time.time(); phase = ""
    while time.time() - t0 < deadline + 120:
        phase = kc("get", "pod", name, "-o", "jsonpath={.status.phase}/{.status.reason}").stdout
        if phase.split("/")[0] in ("Succeeded", "Failed"): break
        time.sleep(2)
    logs = kc("logs", name).stdout
    if os.path.isdir(log_dir):
        with open(f"{log_dir}/{name}.log", "w") as f: f.write(logs)
        init_logs = kc("logs", name, "-c", "prepare").stdout if any(c["name"] == "prepare" for c in spec["spec"].get("initContainers", [])) else ""
        if init_logs:
            with open(f"{log_dir}/{name}.prepare.log", "w") as f: f.write(init_logs)
    gate = [line for line in kc("logs", name, "-c", "netgate").stdout.splitlines() if line.startswith("NETGATE ")] if netgate_enabled() else []
    gate_failed = netgate_enabled() and not (gate and json.loads(gate[-1][8:]).get("ok"))
    pod = {"pod": name, "phase": phase, "wall_s": round(time.time() - t0, 1),
           **({"netgate": json.loads(gate[-1][8:])} if gate else {}),
           **({"infra_error": "netgate: " + (gate[-1][8:] if gate else "no result")} if gate_failed else {})}
    kc("delete", "pod", name, "--wait=false")
    if patch: kc("delete", "configmap", f"{name}-patch", "--ignore-not-found")
    return logs, pod


def main():
    role, cid, name, deadline = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    rest = sys.argv[5:]; cmd = rest[rest.index("--") + 1:]; opts = rest[:rest.index("--")]
    opt = lambda flag, default=None: opts[opts.index(flag) + 1] if flag in opts else default
    patch = opt("--patch")
    extra_env = [o for i, o in enumerate(opts) if i > 0 and opts[i - 1] == "--env"]
    if role == "agent": extra_env.append("RUN_TOKEN=" + os.environ.pop("RUN_TOKEN"))  # not exposed in CLI arguments
    meta = json.load(open(f"/srv/ci/cases/{cid}/meta.json"))
    out_dir = None
    if role == "exec":
        out_dir = f"{OUT_ROOT}/{name}"; os.makedirs(out_dir, exist_ok=True); os.chmod(out_dir, 0o777)
    spec = build_spec(role, cid, name, deadline, cmd, meta, patch, extra_env, tree=opt("--tree"),
                      cpu=opt("--cpu", "3"), memory=opt("--memory", "8Gi"), out_dir=out_dir)
    try:
        with cpu_slots(name, opt("--cpu", "3"), opt("--memory", "8Gi")): logs, pod = run_pod(spec, patch)
    except RuntimeError as e: sys.exit(str(e))
    # Only the final record of each kind belongs to the harness, not an earlier line printed by a command.
    for tag in ("EXECUTOR ", "RESULT "):
        lines = [line for line in logs.splitlines() if line.startswith(tag)]
        if lines: print(lines[-1])
    # A failed gate is an infrastructure error: the main container never started, so there is no EXECUTOR/RESULT line.
    print("POD " + json.dumps(pod))

if __name__ == "__main__":
    main()
