#!/usr/bin/env python3
"""Probe driver of 2026-11-13, runs ON the VM as the lab user. Like the driver of 2026-11-12 (run-probe-pods.py), every pod is
built with the harness's OWN spec builders (cases/pod.py build_spec, cases/prep.py worker_spec); only the command of the
main container is replaced by netwatch.py (mounted from a ConfigMap at /probe) and the CPU/memory *requests* are lowered.
New here: a plan file with many pods run with a fixed concurrency; "runtime": "runc" removes runtimeClassName (same
namespace, same policy, default runtime); "gate" builds the spec with or without the network gate init container
(NETGATE=1/0, see cases/pod.py); the time of the `kubectl apply` is recorded in epoch ms; the pod object is saved at the end.
usage: run-watch-pods.py <run-dir> <case-id> <out-dir> <patch-file> <plan.json>
plan: {"concurrency": N, "pods": [{"name":..., "kind": agent|exec-repro|exec-validate|prep, "runtime": kata|runc, "gate": bool,
       "seconds": S, "interval": I, "only": "label,label" (optional)}]}"""
import json, os, pathlib, subprocess, sys, threading, time
run_dir, cid, out_dir, patch, plan = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]), sys.argv[4], json.load(open(sys.argv[5]))
sys.path.insert(0, run_dir + "/cases"); os.chdir(run_dir); out_dir.mkdir(parents=True, exist_ok=True)
import pod, prep
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
HERE = pathlib.Path(__file__).resolve().parent
kc = lambda *a, **k: subprocess.run(["kubectl", *a], capture_output=True, text=True, **k)
jp = lambda *a: kc(*a).stdout.strip()
targets = {"case_id": cid,
           "node_ip": jp("get", "nodes", "-o", "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}"),
           "gw_pod_ip": jp("-n", "ci-gateway", "get", "pods", "-l", "app=gateway", "-o", "jsonpath={.items[0].status.podIP}"),
           "dns_pod_ip": jp("-n", "kube-system", "get", "pods", "-l", "k8s-app=kube-dns", "-o", "jsonpath={.items[0].status.podIP}")}
meta = json.load(open(f"/srv/ci/cases/{cid}/meta.json")); secret_meta = json.load(open(f"/srv/ci/secret/{cid}/meta.json"))
EX = ["python3", "-u", "/code/executor.py"]; ALLOWED = {"agent": "gwm,gwpm", "prep": "pub,dns", "exec-repro": "", "exec-validate": ""}
build_lock = threading.Lock(); print_lock = threading.Lock()
for ns in ("ci-agent", "ci-exec", "ci-prep"):
    cm = kc("-n", ns, "create", "configmap", "probe-code", f"--from-file={HERE}/netwatch.py", "-o", "yaml", "--dry-run=client").stdout
    subprocess.run(["kubectl", "apply", "-f", "-"], input=cm, text=True, capture_output=True, check=True)

def build(p):
    kind, name, deadline = p["kind"], p["name"], int(p["seconds"]) + 180
    with build_lock:
        os.environ["NETGATE"] = "1" if p.get("gate") else "0"
        if kind == "prep":
            base = pathlib.Path(f"/srv/ci/work/probe-{name}"); (base / "source").mkdir(parents=True, exist_ok=True); (base / "output" / "uv").mkdir(parents=True, exist_ok=True)
            return prep.worker_spec(cid, name, base / "source", base / "output", meta)
        if kind == "agent": return pod.build_spec("agent", cid, name, deadline, ["true"], meta)
        action = {"exec-repro": ["repro", "broken", "1"], "exec-validate": ["validate", "suite"]}[kind]
        return pod.build_spec("exec", cid, name, deadline, EX + action, meta, patch if action[0] == "validate" else None, (), secret_meta)

def one(p):
    name, kind = p["name"], p["kind"]; spec = build(p); ns = spec["metadata"]["namespace"]; c = spec["spec"]["containers"][0]
    if p["runtime"] == "runc": del spec["spec"]["runtimeClassName"]
    if p.get("ns"): spec["metadata"]["namespace"] = ns = p["ns"]   # T3: a namespace whose policy is applied later (needs SA runner and the ConfigMaps)
    if kind == "exec-validate":
        kc("-n", ns, "delete", "configmap", f"{name}-patch", "--ignore-not-found"); kc("-n", ns, "create", "configmap", f"{name}-patch", f"--from-file=patch.diff={patch}")
    original = c["command"]; c["command"] = ["python3", "-u", "/probe/netwatch.py"]
    env = {"PROBE_TARGETS": json.dumps(targets), "PROBE_ROLE": kind, "PROBE_RUNTIME": p["runtime"], "NETWATCH_SECONDS": str(p["seconds"]),
           "NETWATCH_INTERVAL": str(p.get("interval", 0.1)), "NETWATCH_ALLOWED": ALLOWED[kind], "NETWATCH_SLOW": ALLOWED[kind], "NETWATCH_ONLY": p.get("only", ""), "NETWATCH_TIMEOUT": str(p.get("timeout", 0.2))}
    if p.get("ns"): env["NETWATCH_ALLOWED"] = env["NETWATCH_SLOW"] = ""
    if p.get("raw"): env["NETWATCH_RAW"] = "1"
    c.setdefault("env", []).extend({"name": k, "value": v} for k, v in env.items())
    c["volumeMounts"].append({"name": "probe", "mountPath": "/probe", "readOnly": True})
    spec["spec"]["volumes"].append({"name": "probe", "configMap": {"name": "probe-code"}})
    for cont in spec["spec"]["containers"] + spec["spec"].get("initContainers", []):
        if "resources" in cont: cont["resources"]["requests"] = {"cpu": "100m", "memory": "256Mi"}
    (out_dir / f"{name}.spec.json").write_text(json.dumps({"replaced_command": original, "plan": p, "spec": spec}, indent=1))
    a = int(time.time() * 1000); r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), text=True, capture_output=True); b = int(time.time() * 1000)
    if r.returncode:
        (out_dir / f"{name}.log").write_text("APPLY FAILED " + r.stderr); return
    t0 = time.time(); limit = int(p["seconds"]) + 400; started = False
    while time.time() - t0 < limit:   # wait for the main container (or the end of the pod), then follow its log to a file
        st = jp("-n", ns, "get", "pod", name, "-o", "jsonpath={.status.phase} {.status.containerStatuses[0].state.running.startedAt}{.status.containerStatuses[0].state.terminated.startedAt}")
        if st.startswith(("Succeeded", "Failed")) or len(st.split()) > 1: started = True; break
        time.sleep(0.5)
    with open(out_dir / f"{name}.log", "w") as f: subprocess.run(["kubectl", "-n", ns, "logs", "-f", name, "-c", "c"], stdout=f, stderr=subprocess.DEVNULL)
    while time.time() - t0 < limit:
        if jp("-n", ns, "get", "pod", name, "-o", "jsonpath={.status.phase}") in ("Succeeded", "Failed"): break
        time.sleep(1)
    for ic in [x["name"] for x in spec["spec"].get("initContainers", [])]:
        (out_dir / f"{name}.init-{ic}.log").write_text(kc("-n", ns, "logs", name, "-c", ic, "--timestamps").stdout[-20000:])
    pj = kc("-n", ns, "get", "pod", name, "-o", "json").stdout
    (out_dir / f"{name}.pod.json").write_text(json.dumps({"apply_start_ms": a, "apply_end_ms": b, "plan": p, "pod": json.loads(pj) if pj.strip().startswith("{") else None}))
    phase = jp("-n", ns, "get", "pod", name, "-o", "jsonpath={.status.phase}")
    if phase != "Succeeded":
        ev = kc("-n", ns, "get", "events", "--field-selector", f"involvedObject.name={name}", "-o", "custom-columns=T:.lastTimestamp,R:.reason,M:.message", "--no-headers").stdout
        (out_dir / f"{name}.events.txt").write_text(ev)
    n = sum(1 for _ in open(out_dir / f"{name}.log"))
    with print_lock: print(time.strftime("%T", time.gmtime()), name, ns, p["runtime"], "gate" if p.get("gate") else "nogate", phase, f"{n} lines", flush=True)
    kc("-n", ns, "delete", "pod", name, "--wait=false")
    if kind == "exec-validate": kc("-n", ns, "delete", "configmap", f"{name}-patch", "--ignore-not-found")
    if kind == "prep": subprocess.run(["rm", "-rf", f"/srv/ci/work/probe-{name}"])

sem = threading.Semaphore(int(plan.get("concurrency", 1))); threads = []
def guarded(p):
    with sem:
        try: one(p)
        except Exception as e:
            with print_lock: print("ERROR", p["name"], repr(e)[:300], flush=True)
for p in plan["pods"]:
    t = threading.Thread(target=guarded, args=(p,)); t.start(); threads.append(t); time.sleep(float(plan.get("stagger", 0.2)))
[t.join() for t in threads]
print(time.strftime("%T", time.gmtime()), "PLAN_DONE", flush=True)
