#!/usr/bin/env python3
"""Runs ON aip-kata-01 as root. Connects one pod to its sandbox on the host: the runtime handler, and the host
processes attributed to it with their Pss. Same attribution as perf.py: every process whose command line names the
sandbox id, plus (default runtime only) every process in the pod's cgroup.   usage: sandbox.py <pod> [namespace]"""
import glob, json, os, subprocess, sys
os.environ.setdefault("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
pod, ns = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "lab-agent")
sh = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.strip()
def cmdline(p):
    try: return open(f"/proc/{p}/cmdline").read().replace("\0", " ").strip()
    except OSError: return ""
def pss_kb(p):
    try: return next(int(l.split()[1]) for l in open(f"/proc/{p}/smaps_rollup") if l.startswith("Pss:"))
    except (OSError, StopIteration): return 0
sid = sh("crictl", "pods", "--name", pod, "--namespace", ns, "--state", "Ready", "-q", "--no-trunc").split("\n")[0]
info = json.loads(sh("crictl", "inspectp", sid))
handler = info["info"].get("runtimeHandler") or info["status"].get("runtimeHandler") or "(default: runc)"
uid = sh("kubectl", "-n", ns, "get", "pod", pod, "-o", "jsonpath={.metadata.uid}")
procs = {int(p): cmdline(p).split(" ")[0].rsplit("/", 1)[-1] for p in filter(str.isdigit, os.listdir("/proc")) if sid in cmdline(p)}
if "kata" not in handler:
    for f in glob.glob(f"/sys/fs/cgroup/**/*{uid.replace('-', '_')}*/**/cgroup.procs", recursive=True):
        for p in open(f).read().split(): procs.setdefault(int(p), cmdline(p).split(" ")[0].rsplit("/", 1)[-1] or "?")
print(f"pod {pod}   sandbox {sid[:12]}   runtime handler {handler}")
print(f"{'PID':>7}  {'PSS MiB':>8}  HOST PROCESS")
tot = 0
for p, c in sorted(procs.items()):
    k = pss_kb(p); tot += k; print(f"{p:>7}  {k / 1024:>8.1f}  {c}")
print(f"{'total':>7}  {tot / 1024:>8.1f}")
