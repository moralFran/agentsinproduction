#!/usr/bin/env python3
"""Integration driver (2026-11-12), runs ON the VM as the lab user. Re-validates the archived agent patches with the
CURRENT validator (cases/validate.py of the fresh run folder: three fresh suite pods, then three fresh hidden pods).
Reads the archive (attempts-v1/v2.jsonl, patches/v1, v2) and never writes to it. Byte-identical patches of one case are
run once; the result is mapped to every attempt that produced them. Resumable: a patch with a stored result is skipped.
usage: revalidate.py <archive-dir> <run-dir> <out-dir> <parallel> <case-id,...>   (cases are processed in the order given)"""
import concurrent.futures, hashlib, json, pathlib, subprocess, sys, threading, time
archive, run_dir, out = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3]); parallel = int(sys.argv[4]); cases = sys.argv[5].split(",")
out.mkdir(parents=True, exist_ok=True); lock = threading.Lock()
jobs = {}
for version in ("v1", "v2"):
    for line in open(archive / "results" / f"attempts-{version}.jsonl"):
        a = json.loads(line); patch = archive / "results" / "patches" / version / f"{a['run']}.diff"
        data = patch.read_bytes() if patch.exists() else b""
        if not data.strip(): continue
        digest = hashlib.sha256(data).hexdigest()
        job = jobs.setdefault((a["case"], digest), {"case": a["case"], "sha256": digest, "patch": str(patch), "runs": []})
        job["runs"].append(a["run"])
todo = [j for c in cases for j in jobs.values() if j["case"] == c]
print(f"{sum(len(j['runs']) for j in todo)} attempts, {len(todo)} distinct patches in {len(cases)} cases", flush=True)

def one(job):
    target = out / job["case"] / f"{job['sha256'][:12]}.json"
    if target.exists(): return job, json.loads(target.read_text())["result"], 0.0
    target.parent.mkdir(parents=True, exist_ok=True); t0 = time.time()
    prefix = f"rv-{hashlib.md5(job['case'].encode()).hexdigest()[:6]}-{job['sha256'][:10]}"
    p = subprocess.run([sys.executable, "cases/validate.py", job["case"], job["patch"], prefix], cwd=run_dir, capture_output=True, text=True)
    result = next((json.loads(l[9:]) for l in reversed(p.stdout.splitlines()) if l.startswith("EXECUTOR ")), None)
    record = {"case": job["case"], "sha256": job["sha256"], "runs": job["runs"], "pod_prefix": prefix, "validator_rc": p.returncode,
              "wall_s": round(time.time() - t0, 1), "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "result": result,
              "stderr_tail": p.stderr[-500:]}
    if result is not None: target.write_text(json.dumps(record, indent=1))      # no result: left for a retry, kept in the journal
    with lock:
        with open(out / "revalidation.jsonl", "a") as f: f.write(json.dumps(record) + "\n")
    return job, result, record["wall_s"]

with concurrent.futures.ThreadPoolExecutor(parallel) as pool:
    for job, result, wall in pool.map(one, todo):
        r = result or {}
        print(time.strftime("%H:%M:%S", time.gmtime()), job["case"], job["sha256"][:12], ",".join(job["runs"]), "->", r.get("outcome"),
              "suite", r.get("suite_pass"), "hidden", r.get("hidden_pass"), f"{wall:.0f}s", (r.get("why") or "")[:100], flush=True)
print("DONE", flush=True)
