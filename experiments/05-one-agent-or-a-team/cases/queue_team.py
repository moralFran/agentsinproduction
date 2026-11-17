#!/usr/bin/env python3
"""Runs ON aip-ci-01. One queue for the reproduction samples of several tasks (criteria E1), packed by CPU: a sample
starts when the sum of the CPU limits of ALL running pods of the lab plus its own stays within the budget
(team_host.cpu_slots; /srv/ci/queue.cpus, default 8 = the VM's vCPUs).
Resumable: a sample whose file exists in /srv/ci/repro/<T#>/ is skipped. Order: the commit jobs of every task first
(minutes each; they decide whether a task has an F2P case), then the area jobs, task by task in the order given.
usage: queue_team.py T2 T3 ... [--reps 3] [--cpus 8] [--mem 28]      (/srv/ci/queue.cpus, when present, overrides --cpus while running)
            (one line per finished sample; ends with QUEUE DONE)"""
import os, sys
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]
import importlib.util, json, pathlib, threading, time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("team_host", HERE / "team_host.py"); host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
a = sys.argv[1:]; opt = lambda flag, default: a[a.index(flag) + 1] if flag in a else default
tasks = [x for x in a if x.startswith("T")]; reps = int(opt("--reps", "3")); CPUS = float(opt("--cpus", "8")); MEM = float(opt("--mem", "28"))
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
gi = lambda m: float(str(m).replace("Gi", ""))

pending = []
for scope in ("commit", "area"):
    for tid in tasks:
        for rep in range(1, reps + 1):
            for tree in ("baseline", "gold"):
                for job in host.secret_meta(tid)["jobs"]:
                    if job["scope"] != scope: continue
                    f = host.ROOT / "repro" / tid / f"{tree}-{job['name']}-{rep}.json"
                    if f.exists(): continue
                    c, m = host.resources(job)
                    pending.append({"tid": tid, "tree": tree, "job": job, "rep": rep, "file": f, "cpu": float(c), "mem": gi(m)})
# Order: (1) every commit job; (2) the FIRST sample of every area job on both trees, for every task (a time for each
# suite and a first look at what fails on both trees, early); (3) samples 2 and 3 of the area jobs, task by task.
order = {t: i for i, t in enumerate(tasks)}
pending.sort(key=lambda p: (0, 0, 0) if p["job"]["scope"] == "commit" else (1, 0, order[p["tid"]]) if p["rep"] == 1 else (2, order[p["tid"]], p["rep"]))
print(f"QUEUE {len(pending)} samples, {sum(p['cpu'] for p in pending):.0f} CPU-slots, tasks {tasks}", flush=True)
lock = threading.Lock(); running = []; done = 0


def work(item):
    global done
    t = time.time(); tid, tree, job, rep = item["tid"], item["tree"], item["job"], item["rep"]
    try:
        r = host.sample(tid, tree, job, host.pod_name("rp", tid, tree, job["name"], rep))
        r.update(tree=tree, job=job["name"], rep=rep, started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), parallel="queue", queue_cpus=CPUS)
        item["file"].parent.mkdir(parents=True, exist_ok=True)
        tmp = item["file"].with_suffix(".tmp"); tmp.write_text(json.dumps(r)); tmp.rename(item["file"])
        e = r["executor"]
        line = (f"SAMPLE {tid} {tree} {job['name']} #{rep}: {e.get('outcome')} counts={e.get('counts')} file_errors={e.get('file_errors')} "
                f"tool={((e.get('tool') or {}).get('s'))}s pod={r['pod'].get('wall_s')}s {e.get('why', '')[:160]}")
    except Exception as x:                                   # keep the queue alive; the sample stays pending for a rerun
        line = f"SAMPLE {tid} {tree} {job['name']} #{rep}: QUEUE ERROR {type(x).__name__}: {str(x)[:200]}"
    with lock:
        running.remove(item); done += 1
        print(f"{time.strftime('%H:%M:%S', time.gmtime())} [{done}] {line}", flush=True)


threads = []
# Samples start in queue order; each waits inside host.sample() for its share of the VM-wide CPU budget. At most
# MAXWAIT threads wait at a time, so the order of the queue is kept apart from small jobs slipping into free slots.
MAXWAIT = 6
while pending:
    with lock: n = len(running)
    if n < MAXWAIT:
        item = pending.pop(0)
        with lock: running.append(item)
        th = threading.Thread(target=work, args=(item,)); th.start(); threads.append(th)
    else: time.sleep(3)
for th in threads: th.join()
print("QUEUE DONE", flush=True)
