#!/usr/bin/env python3
"""Offline check: would the "restricted" Pod Security level refuse a pod this experiment creates?
It renders every pod template of the folder the way the scripts do (placeholders filled in, both runtimes) and applies
the rules of the restricted level as the Kubernetes documentation lists them (Pod Security Standards). It also checks
that lab-agent and lab-validate carry the enforce label. This is a reading of the rules, written here; the cluster's
own admission is the authority. To ask it:  check_restricted.py --render <dir> && kubectl apply --dry-run=server -f <dir>
usage: check_restricted.py [--render <dir>] [k8s-folder]      exit 1 if a pod in an enforcing namespace would be refused
Needs a YAML parser: PyYAML if it is installed, otherwise ruby."""
import json, os, subprocess, sys
args = sys.argv[1:]; render = None
if args[:1] == ["--render"]: render, args = args[1], args[2:]
K8S = args[0] if args else os.path.dirname(os.path.abspath(__file__))

def load(text):
    try:
        import yaml
        return [d for d in yaml.safe_load_all(text) if d]
    except ImportError:
        out = subprocess.run(["ruby", "-ryaml", "-rjson", "-e", "puts JSON.generate(YAML.load_stream(STDIN.read).compact)"], input=text, capture_output=True, text=True, check=True).stdout
        return json.loads(out)

FILL = {"RUN_ID\"": "check\"", "RESULT_NONCE_VALUE": "0" * 32, "NONCE_VALUE": "0" * 32, "SLEEP_SECONDS": "600",
        "VALIDATOR_ARGS": '["python3", "/validator/validate.py", "baseline"]'}
def renders(name, text):
    """-> [(label, text)] : the template as the scripts submit it, on each runtime it is used with."""
    for k, v in FILL.items(): text = text.replace(k, v)
    text = text.replace("POD_NAME", "check").replace("metadata: {name: NAME,", "metadata: {name: check,")
    if "RUNTIME_LINE" in text: return [(f"{name} (runc)", text.replace("RUNTIME_LINE", "")), (f"{name} (kata)", text.replace("RUNTIME_LINE", "runtimeClassName: kata-qemu"))]
    if "runtimeClassName: RUNTIME" in text:
        return [(f"{name} (runc)", "\n".join(l for l in text.splitlines() if "runtimeClassName" not in l)), (f"{name} (kata)", text.replace("RUNTIME", "kata-qemu"))]
    return [(name, text)]

OK_VOLUMES = {"configMap", "csi", "downwardAPI", "emptyDir", "ephemeral", "persistentVolumeClaim", "projected", "secret"}
def violations(pod):
    spec = pod.get("spec", {}); psc = spec.get("securityContext") or {}; out = []
    for f in ("hostNetwork", "hostPID", "hostIPC"):
        if spec.get(f): out.append(f"{f} is set")
    for v in spec.get("volumes") or []:
        kinds = set(v) - {"name"}
        if not kinds <= OK_VOLUMES: out.append(f"volume {v.get('name')}: type {sorted(kinds - OK_VOLUMES)} not allowed")
    if psc.get("runAsUser") == 0: out.append("pod runAsUser is 0")
    if psc.get("sysctls"): out.append("sysctls set (not checked here)")
    for kind in ("initContainers", "containers", "ephemeralContainers"):
        for c in spec.get(kind) or []:
            sc = c.get("securityContext") or {}; n = f"{kind[:-1]} {c.get('name')}"
            if sc.get("privileged"): out.append(f"{n}: privileged")
            if sc.get("allowPrivilegeEscalation") is not False: out.append(f"{n}: allowPrivilegeEscalation is not false")
            if "ALL" not in ((sc.get("capabilities") or {}).get("drop") or []): out.append(f"{n}: capabilities.drop does not include ALL")
            if set((sc.get("capabilities") or {}).get("add") or []) - {"NET_BIND_SERVICE"}: out.append(f"{n}: adds capabilities")
            if sc.get("runAsNonRoot") is False or not (sc.get("runAsNonRoot") or psc.get("runAsNonRoot")): out.append(f"{n}: runAsNonRoot is not true")
            if sc.get("runAsUser") == 0: out.append(f"{n}: runAsUser is 0")
            if (sc.get("seccompProfile") or psc.get("seccompProfile") or {}).get("type") not in ("RuntimeDefault", "Localhost"): out.append(f"{n}: no seccompProfile RuntimeDefault/Localhost")
            if sc.get("procMount") not in (None, "Default"): out.append(f"{n}: procMount")
            if any(p.get("hostPort") for p in c.get("ports") or []): out.append(f"{n}: hostPort")
    return out
def extras(pod):
    """Not part of the restricted level, asked for by the fourth review: a read-only root filesystem."""
    return [f"container {c.get('name')}: root filesystem is writable" for k in ("initContainers", "containers") for c in pod.get("spec", {}).get(k) or []
            if not (c.get("securityContext") or {}).get("readOnlyRootFilesystem")]

enforcing, pods = set(), []
for f in sorted(os.listdir(K8S)):
    if not f.endswith(".yaml"): continue
    for label, text in renders(f, open(os.path.join(K8S, f)).read()):
        for d in load(text):
            if d.get("kind") == "Namespace" and (d["metadata"].get("labels") or {}).get("pod-security.kubernetes.io/enforce") == "restricted": enforcing.add(d["metadata"]["name"])
            specs = [d] if d.get("kind") == "Pod" else [{"metadata": d["metadata"], "spec": d["spec"]["template"]["spec"]}] if d.get("kind") == "Deployment" else []
            for pod in specs: pods.append((label, d["metadata"].get("namespace", "default"), pod))
        if render and "kind: Pod" in text:
            os.makedirs(render, exist_ok=True); open(os.path.join(render, label.replace(" ", "-").replace("(", "").replace(")", "") + ".yaml"), "w").write(text)
bad = 0
print(f"namespaces enforcing 'restricted': {', '.join(sorted(enforcing)) or 'none'}")
for want in ("lab-agent", "lab-validate"):
    if want not in enforcing: print(f"NOTE {want} does not carry pod-security.kubernetes.io/enforce: restricted")
for label, ns, pod in pods:
    v, e = violations(pod), extras(pod); enforced = ns in enforcing; bad += bool(v) and enforced
    tag = "ok    " if not v else "REFUSE" if enforced else "would "
    print(f"{tag} {label:34} {ns:13} " + ("meets restricted" if not v else "; ".join(v)) + (f"   [also: {'; '.join(e)}]" if e and enforced else ""))
sys.exit(1 if bad else 0)
