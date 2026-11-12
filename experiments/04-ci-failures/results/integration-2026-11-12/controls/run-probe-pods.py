#!/usr/bin/env python3
"""Integration probe driver (2026-11-12), runs ON the VM as the lab user. Builds each pod with the harness's OWN spec builders
(cases/pod.py build_spec, cases/prep.py worker_spec) so runtime class, user, security context, mounts and namespace are
the real ones; then replaces only the command of the main container with netprobe.py (mounted from a ConfigMap at /probe)
and lowers the CPU/memory *requests* so the probes fit beside running work (limits unchanged). The init container of
validation pods is left untouched: it runs the real validate-prepare.
usage: run-probe-pods.py <run-dir> <case-id> <out-dir> <patch-file> <which,...>
which: ctl (namespace default, no policy), prep, agent, exec-repro, exec-fixed, exec-validate-suite, exec-validate-hidden
env: PROBE_FILE (default netprobe.py; nettime.py measures when the policy starts to apply), NAME_SUFFIX (for repeated runs)"""
import json, os, pathlib, subprocess, sys, time
run_dir, cid, out_dir, patch, which = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]), sys.argv[4], sys.argv[5].split(",")
sys.path.insert(0, run_dir + "/cases"); os.chdir(run_dir)
import pod, prep
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
HERE = pathlib.Path(__file__).resolve().parent
PROBE = os.environ.get("PROBE_FILE", "netprobe.py"); SUFFIX = os.environ.get("NAME_SUFFIX", "")
kc = lambda *a, **k: subprocess.run(["kubectl", *a], capture_output=True, text=True, **k)
jp = lambda *a: kc(*a).stdout.strip()
targets = {"case_id": cid,
           "node_ip": jp("get", "nodes", "-o", "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}"),
           "gw_pod_ip": jp("-n", "ci-gateway", "get", "pods", "-l", "app=gateway", "-o", "jsonpath={.items[0].status.podIP}"),
           "other_pod_ip": jp("-n", "kube-system", "get", "pods", "-l", "k8s-app=metrics-server", "-o", "jsonpath={.items[0].status.podIP}"),
           "dns_pod_ip": jp("-n", "kube-system", "get", "pods", "-l", "k8s-app=kube-dns", "-o", "jsonpath={.items[0].status.podIP}")}
meta = json.load(open(f"/srv/ci/cases/{cid}/meta.json")) if os.path.exists(f"/srv/ci/cases/{cid}/meta.json") else {"language": "Go", "id": cid}
secret_meta = json.load(open(f"/srv/ci/secret/{cid}/meta.json")) if os.path.exists(f"/srv/ci/secret/{cid}/meta.json") else {}
EX = ["python3", "-u", "/code/executor.py"]; DEADLINE = int(os.environ.get("PROBE_DEADLINE", "300"))

def build(kind, name):
    if kind == "ctl":
        return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "default"}, "spec": {
            "runtimeClassName": "kata-qemu", "automountServiceAccountToken": False, "restartPolicy": "Never", "activeDeadlineSeconds": int(os.environ.get("PROBE_DEADLINE", "300")),
            "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000},
            "containers": [{"name": "c", "image": "aip-ci-box:1", "imagePullPolicy": "Never", "command": ["true"], "volumeMounts": []}], "volumes": []}}
    if kind == "prep":
        base = pathlib.Path(f"/srv/ci/work/probe-{name}"); (base / "source").mkdir(parents=True); (base / "output" / "uv").mkdir(parents=True)
        return prep.worker_spec(cid, name, base / "source", base / "output", meta)
    if kind == "agent": return pod.build_spec("agent", cid, name, DEADLINE, ["true"], meta)
    action = {"exec-repro": ["repro", "broken", "1"], "exec-fixed": ["repro", "fixed", "1"],
              "exec-validate-suite": ["validate", "suite"], "exec-validate-hidden": ["validate", "hidden"]}[kind]
    return pod.build_spec("exec", cid, name, DEADLINE, EX + action, meta, patch if action[0] == "validate" else None, (), secret_meta)

for kind in which:
    name = f"probe-{kind}{SUFFIX}"; spec = build(kind, name); ns = spec["metadata"]["namespace"]; c = spec["spec"]["containers"][0]
    kc("-n", ns, "delete", "pod", name, "--ignore-not-found", "--wait=true")
    cm = kc("-n", ns, "create", "configmap", "probe-code", f"--from-file={HERE}/netprobe.py", f"--from-file={HERE}/nettime.py", f"--from-file={HERE}/netflap.py", "-o", "yaml", "--dry-run=client").stdout
    subprocess.run(["kubectl", "apply", "-f", "-"], input=cm, text=True, capture_output=True, check=True)
    if kind.startswith("exec-validate"):
        kc("-n", ns, "delete", "configmap", f"{name}-patch", "--ignore-not-found")
        r = kc("-n", ns, "create", "configmap", f"{name}-patch", f"--from-file=patch.diff={patch}"); assert r.returncode == 0, r.stderr
    original_command = c["command"]
    c["command"] = ["python3", "-u", f"/probe/{PROBE}"]
    c.setdefault("env", []).extend([{"name": "PROBE_TARGETS", "value": json.dumps(targets)}, {"name": "PROBE_ROLE", "value": kind}])
    for key in ("NETTIME_SECONDS", "NETFLAP_SECONDS"):
        if os.environ.get(key): c["env"].append({"name": key, "value": os.environ[key]})
    c["volumeMounts"].append({"name": "probe", "mountPath": "/probe", "readOnly": True})
    spec["spec"]["volumes"].append({"name": "probe", "configMap": {"name": "probe-code"}})
    for cont in spec["spec"]["containers"] + spec["spec"].get("initContainers", []):
        if "resources" in cont: cont["resources"]["requests"] = {"cpu": "200m", "memory": "512Mi"}
    (out_dir / f"{name}.spec.json").write_text(json.dumps({"replaced_command": original_command, "spec": spec}, indent=1))
    r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), text=True, capture_output=True)
    if r.returncode: (out_dir / f"{name}.log").write_text("APPLY FAILED " + r.stderr); print(name, "apply failed", r.stderr[-300:]); continue
    t0 = time.time(); phase = ""
    while time.time() - t0 < DEADLINE + 240:
        phase = jp("-n", ns, "get", "pod", name, "-o", "jsonpath={.status.phase}/{.status.reason}")
        if phase.split("/")[0] in ("Succeeded", "Failed"): break
        time.sleep(2)
    logs = kc("-n", ns, "logs", name, "--all-containers", "--prefix").stdout
    times = jp("-n", ns, "get", "pod", name, "-o", "jsonpath=created {.metadata.creationTimestamp} main-started {.status.containerStatuses[0].state.terminated.startedAt} main-finished {.status.containerStatuses[0].state.terminated.finishedAt}")
    status = jp("-n", ns, "get", "pod", name, "-o", "jsonpath={range .status.initContainerStatuses[*]}init {.name} exit {.state.terminated.exitCode} {end}{range .status.containerStatuses[*]}main {.name} exit {.state.terminated.exitCode} {.state.waiting.reason}{end}")
    events = "" if phase.startswith("Succeeded") else kc("-n", ns, "get", "events", "--field-selector", f"involvedObject.name={name}", "-o", "custom-columns=R:.reason,M:.message", "--no-headers").stdout
    (out_dir / f"{name}.log").write_text(f"# pod {name} namespace {ns} phase {phase} wall {time.time() - t0:.0f}s\n# {status}\n# {times}\n{logs}\n{events}")
    print(name, ns, phase, status, f"{len(logs.splitlines())} log lines")
    kc("-n", ns, "delete", "pod", name, "--wait=false")
    if kind.startswith("exec-validate"): kc("-n", ns, "delete", "configmap", f"{name}-patch", "--ignore-not-found")
    if kind == "prep": subprocess.run(["rm", "-rf", f"/srv/ci/work/probe-{name}"])
