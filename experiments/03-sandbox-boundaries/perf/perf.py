#!/usr/bin/env python3
"""Runs ON aip-kata-01 (as root). Start time and idle memory per runtime.

Start: N pods per runtime, alternating, one sandbox at a time, image already on the node. Clock: this host only.
  t0 = the moment `kubectl create` RETURNED (the API had already accepted the pod; the call itself took ~175 ms and
       is recorded per start as create_call_ms, so "from the start of the create call" = start_ms + create_call_ms)
  t1 = the pod's own process (python3) made an HTTP request to a collector on this host
  start_ms = t1 - t0. Image pulls are outside this number (image is preloaded; pulls reported separately).
Memory: after READY + IDLE_S seconds, sum of Pss (smaps_rollup) of the host processes that belong to that sandbox:
  runc: every process in the pod's cgroup (pause + app) + its containerd-shim-runc-v2
  kata: qemu + containerd-shim-kata-v2 + virtiofsd of that sandbox (the guest's memory is inside qemu; not added again)
Pss counts resident memory attributed to processes; page cache and kernel memory are not fully covered."""
import glob, json, os, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
if len(sys.argv) < 3 or os.path.exists(sys.argv[2]):      # results/perf.jsonl is the collection of 2026-11-11
    sys.exit("usage: perf.py <N> <new output file, e.g. results/perf-r4.jsonl>   (an existing file is never overwritten)")
OUT = sys.argv[2]
IDLE_S, NS, PORT, IMAGE = 15, "lab-perf", 9099, "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
HOST = os.environ["NODE_IP"]            # from lab.env
# The image name is written exactly as in the other manifests ("python:...", no registry prefix). With imagePullPolicy
# Never the kubelet (image pull records, k8s 1.37) accepts a local image only under the name it was first pulled with;
# "docker.io/library/python:..." is the same image and is refused with ErrImageNeverPull.
os.environ.setdefault("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")   # run as root (reads /proc of other users)
ready = {}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        ready.setdefault(self.path.rsplit("/", 1)[-1], time.monotonic())
        self.send_response(200); self.send_header("content-length", "0"); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer((HOST, PORT), H).serve_forever, daemon=True).start()

def sh(*a, inp=None, check=True):
    return subprocess.run(a, input=inp, capture_output=True, text=True, check=check).stdout.strip()

def pss_kb(pid):
    try:
        for l in open(f"/proc/{pid}/smaps_rollup"):
            if l.startswith("Pss:"): return int(l.split()[1])
    except OSError: pass
    return 0

def cmdline(pid):
    try: return open(f"/proc/{pid}/cmdline").read().replace("\0", " ").strip()
    except OSError: return ""

def sandbox_procs(name, uid, rt):
    sid = sh("crictl", "pods", "--name", name, "--state", "Ready", "-q", "--no-trunc").split("\n")[0]
    procs = {}
    for p in filter(str.isdigit, os.listdir("/proc")):          # processes whose command line names this sandbox id
        c = cmdline(p)
        if sid and sid in c: procs[int(p)] = c.split(" ")[0].rsplit("/", 1)[-1]
    if rt == "runc":                                             # plus everything in the pod's cgroup
        for f in glob.glob(f"/sys/fs/cgroup/**/*{uid.replace('-', '_')}*/**/cgroup.procs", recursive=True):
            for p in open(f).read().split():
                procs.setdefault(int(p), cmdline(p).split(" ")[0].rsplit("/", 1)[-1] or "?")
    return sid, procs

POD = """apiVersion: v1
kind: Pod
metadata: {{name: {name}, namespace: {ns}}}
spec:
  {rc}
  automountServiceAccountToken: false
  restartPolicy: Never
  terminationGracePeriodSeconds: 1
  containers:
  - name: app
    image: {image}
    imagePullPolicy: Never
    command: ["python3", "-c", "import urllib.request,time; urllib.request.urlopen('http://{host}:{port}/ready/{name}', timeout=10); time.sleep(86400)"]
    resources: {{limits: {{cpu: '1', memory: 512Mi}}}}
"""
sh("kubectl", "create", "namespace", NS, check=False)
with open(OUT, "x") as out:
    for i in range(1, N + 1):
        for rt in (("runc", "kata-qemu") if i % 2 else ("kata-qemu", "runc")):   # alternate which runtime goes first
            name = f"p-{rt.split('-')[0]}-{i:02d}"
            rc = "" if rt == "runc" else f"runtimeClassName: {rt}"
            y = POD.format(name=name, ns=NS, rc=rc, image=IMAGE, host=HOST, port=PORT)
            row = {"i": i, "runtime": rt, "pod": name}
            sh("kubectl", "apply", "--dry-run=client", "-f", "-", inp=y)   # warm kubectl's discovery cache, not timed
            t_before = time.monotonic()
            sh("kubectl", "create", "-f", "-", inp=y)
            t0 = time.monotonic()
            while name not in ready and time.monotonic() - t0 < 120: time.sleep(0.002)
            if name not in ready:
                row["outcome"] = "start_timeout"
            else:
                row.update(outcome="ok", start_ms=round((ready[name] - t0) * 1000), create_call_ms=round((t0 - t_before) * 1000))
                time.sleep(IDLE_S)
                uid = sh("kubectl", "-n", NS, "get", "pod", name, "-o", "jsonpath={.metadata.uid}")
                sid, procs = sandbox_procs(name, uid, rt)
                per = {}
                for pid, comm in procs.items(): per[comm] = per.get(comm, 0) + pss_kb(pid)
                row.update(sandbox=sid[:12], pss_kb_total=sum(per.values()), pss_kb_by_process=per, n_procs=len(procs))
            out.write(json.dumps(row) + "\n"); out.flush(); print(json.dumps(row), flush=True)
            sh("kubectl", "-n", NS, "delete", "pod", name, "--wait=true", "--timeout=120s", check=False)
            time.sleep(2)
