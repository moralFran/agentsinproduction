#!/usr/bin/env python3
"""Trusted host orchestrator of experiment 05 (A-v07). Runs ON aip-ctx-01 as the lab user, from the experiment folder.
Every sample is one fresh Kata pod in ci-exec (no network; cases/pod.py + executor/team.py).

  repro <T#> [--reps 3] [--parallel P] [--trees baseline,gold] [--jobs a,b] [--kinds flutter,jest] [--force]
        criteria E1: every job of the task, N samples on the BASELINE tree (snapshot = parent + the commit's tests) and
        N on GOLD (baseline + the owner's fix). Raw samples go to /srv/ci/repro/<T#>/. Resumable: existing samples are kept.
  derive <T#>
        from the 3 + 3 samples: per test case F2P (commit test files; fails 3/3 on baseline, passes 3/3 on gold), P2P
        (area suites; passes 3/3 on both), excluded (fails on both), unstable (mixed). Writes
        /srv/ci/secret/<T#>/cases.json (the lists the validator uses), /srv/ci/cases/<T#>/failure.txt (baseline output
        of the commit's test files, for the agent) and prints the summary. `--out DIR` also writes <T#>.json there.
  shell <T#> <tree> '<command>' [--cpu N] [--memory M]
        one pod, one command in the prepared tree; prints its output (probes and offline proofs).
cases/validate.py is the validator entry point for attempts."""
import os, sys
# cases/ still holds experiment 04's queue.py, which would shadow the standard library's `queue` (needed by
# concurrent.futures) because a script's own directory comes first on sys.path. Drop that entry before importing.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]
import concurrent.futures, importlib.util, json, pathlib, re, shutil, time

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("team_pod", HERE / "pod.py"); pod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pod)
ROOT = pathlib.Path(os.environ.get("TEAM_ROOT", "/srv/ci"))          # TEAM_ROOT: local tests only
# CPU / memory limits of one sample, per job kind (the Kata VM gets this many vCPUs). Overridable: TEAM_RES_<KIND>=cpu,mem
RES = {"flutter": ("4", "10Gi"), "flutter-commit": ("2", "4Gi"), "jest": ("2", "4Gi"), "jest-e2e-functions": ("3", "6Gi"), "shell": ("4", "10Gi")}
DEADLINE = {"flutter": 4200, "jest": 6000, "jest-e2e-functions": 4200, "shell": 2400}


def resources(job):
    kind = "flutter-commit" if job["kind"] == "flutter" and int(job.get("procs", 1)) == 1 else job["kind"]
    v = os.environ.get("TEAM_RES_" + kind.upper().replace("-", "_"))
    return tuple(v.split(",")) if v else RES[kind]


def last_record(output, tag):
    for line in reversed(output.splitlines()):
        if line.startswith(tag):
            try: return json.loads(line[len(tag):])
            except (ValueError, TypeError): return {}
    return {}


cpu_slots = pod.cpu_slots       # the VM-wide CPU and memory ledger lives in pod.py, so `pod.py agent` goes through it too


def sample(tid, tree, job, name, patch=None, cpu=None, memory=None):
    """One pod. Returns {"executor": summary line, "pod": pod record, "result": the per-case result file or None}."""
    c, m = resources(job)
    with cpu_slots(name, cpu or c, memory or m): return _sample(tid, tree, job, name, patch, cpu or c, memory or m)


def keep_result(name, result, ex, rec):
    """criteria E22: the whole result of every sample is kept (per-case status, file errors, per-file exit codes), so a
    verdict can be recomputed from outside. One gzip per pod name under KEEP_RESULTS (default /srv/ci/keep; "" = off,
    local tests only); a name used again gets a numbered suffix, nothing is overwritten. Written to a temporary file,
    synced, renamed, then read back. Any failure raises OSError: the caller must not delete the original and must not
    return a result (a verdict without its evidence is not a verdict). Returns the path written, or None when off."""
    keep = os.environ.get("KEEP_RESULTS", str(ROOT / "keep"))
    if not keep: return None
    import gzip
    os.makedirs(keep, exist_ok=True); path = os.path.join(keep, name + ".json.gz"); n = 1
    while os.path.exists(path): n += 1; path = os.path.join(keep, f"{name}.{n}.json.gz")
    body = json.dumps({"pod": name, "kept_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "executor": ex, "phase": rec.get("phase"), "result": result})
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb") as f: f.write(body.encode())
            raw.flush(); os.fsync(raw.fileno())
        os.replace(tmp, path)
        with gzip.open(path, "rt") as f:
            if json.load(f)["pod"] != name: raise OSError("kept file does not read back")
    except (OSError, ValueError, EOFError) as e:
        try: os.remove(tmp)
        except OSError: pass
        raise OSError(f"could not keep the result of {name}: {e}")
    return path


def _sample(tid, tree, job, name, patch, cpu, memory):
    meta = json.load(open(ROOT / "cases" / tid / "meta.json"))
    out_dir = ROOT / "out" / name
    if out_dir.exists(): shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True); os.chmod(out_dir, 0o777)
    spec = pod.build_spec("exec", tid, name, DEADLINE[job["kind"]], ["python3", "-u", "/code/team.py", "run"], meta, patch,
                          extra_env=["JOB=" + json.dumps(job)], tree=tree, cpu=cpu, memory=memory, out_dir=str(out_dir))
    try: logs, rec = pod.run_pod(spec, patch)
    except RuntimeError as e: return {"executor": {"outcome": "infra_error", "why": str(e)[-300:]}, "pod": {}, "result": None}
    ex = last_record(logs, "EXECUTOR ")
    try: result = json.load(open(out_dir / "result.json"))
    except (OSError, ValueError): result = None
    if rec.get("infra_error") or not str(rec.get("phase", "")).startswith("Succeeded/") or not ex:
        reason = str(rec.get("phase", ""))
        ex = {"outcome": "timeout" if "DeadlineExceeded" in reason else "infra_error",
              "why": rec.get("infra_error") or reason or "pod produced no completion record", **{k: v for k, v in ex.items() if k not in ("outcome", "why")}}
    try: keep_result(name, result, ex, rec)
    except OSError as e:     # E22: no evidence kept => not a result; the original stays in out_dir for a person to look at
        return {"executor": {"outcome": "infra_error", "why": f"{e}; original left in {out_dir}"}, "pod": rec, "result": None}
    shutil.rmtree(out_dir, ignore_errors=True)
    return {"executor": ex, "pod": rec, "result": result, "limits": {"cpu": cpu, "memory": memory}}


def pod_name(prefix, tid, tree, job, rep):
    return re.sub(r"[^a-z0-9-]", "-", f"{prefix}-{tid}-{tree[:1]}-{job}-{rep}".lower())[:63].strip("-")


def secret_meta(tid): return json.load(open(ROOT / "secret" / tid / "meta.json"))


# ------------------------------------------------------------------------------------------------------- repro
def repro(tid, reps=3, parallel=1, trees=("baseline", "gold"), only=None, force=False, kinds=None):
    jobs = [j for j in secret_meta(tid)["jobs"] if (not only or j["name"] in only) and (not kinds or j["kind"] in kinds)]
    outdir = ROOT / "repro" / tid; outdir.mkdir(parents=True, exist_ok=True)
    todo = []
    for rep in range(1, reps + 1):
        for tree in trees:
            for job in jobs:
                f = outdir / f"{tree}-{job['name']}-{rep}.json"
                if f.exists() and not force: continue
                todo.append((tree, job, rep, f))
    def one(item):
        tree, job, rep, f = item; t = time.time()
        r = sample(tid, tree, job, pod_name("rp", tid, tree, job["name"], rep))
        r.update(tree=tree, job=job["name"], rep=rep, started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), parallel=parallel)
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(r)); tmp.rename(f)
        e = r["executor"]
        print(f"SAMPLE {tid} {tree} {job['name']} #{rep}: {e.get('outcome')} counts={e.get('counts')} file_errors={e.get('file_errors')} "
              f"tool={((e.get('tool') or {}).get('s'))}s pod={r['pod'].get('wall_s')}s {e.get('why', '')[:160]}", flush=True)
        return r
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool: list(pool.map(one, todo))
    print(f"REPRO {tid}: {len(todo)} samples run", flush=True)


def statuses(sample_result, universe_files):
    """case -> status for one sample; a case missing from a file that failed to load/run counts as fail."""
    res = sample_result.get("result") or {}
    return res.get("cases") or {}, set((res.get("file_errors") or {}).keys())


def case_file(key): return key.split("::", 1)[0]


# criteria E9 (owner, 2026-11-15): performance tests are not executed and are in no list. executor/team.py leaves this
# case out of every run from 19:15 UTC on; samples taken before that still hold it, so it is dropped here by key and
# reported under "not_run_performance".
PERFORMANCE_CASES = {"test/redacted_timing_test.dart::Timing group timing case (name redacted)"}


def classify(tid, reps=3):
    sm = secret_meta(tid); commit_tests = set(sm["tests_put_back"]); outdir = ROOT / "repro" / tid
    out = {"id": tid, "n": sm["n"], "snapshot_commit": sm["snapshot_commit"], "snapshot_tar_sha256": sm["snapshot_tar_sha256"], "reps": reps,
           "jobs": {}, "f2p": [], "p2p": [], "excluded_fail_both": [], "unstable": [], "skipped": [], "broken_by_gold": [],
           "fixed_outside_commit_tests": [], "commit_tests_pass_both_out_of_scope": [], "not_run_performance": [], "problems": []}
    failure_blocks = []
    for job in sm["jobs"]:
        name = job["name"]; S = {"baseline": [], "gold": []}
        info = {"kind": job["kind"], "scope": job["scope"], "area": job["area"], "in_scope": job.get("in_scope", job["scope"] == "area"), "samples": []}
        for tree in ("baseline", "gold"):
            for rep in range(1, reps + 1):
                f = outdir / f"{tree}-{name}-{rep}.json"
                if not f.exists(): out["problems"].append(f"missing sample {tree}-{name}-{rep}"); continue
                r = json.load(open(f)); e = r["executor"]
                info["samples"].append({"tree": tree, "rep": rep, "outcome": e.get("outcome"), "tool_s": (e.get("tool") or {}).get("s"), "tool_rc": (e.get("tool") or {}).get("rc"),
                                        "pod_wall_s": r["pod"].get("wall_s"), "counts": e.get("counts"), "file_errors": e.get("file_errors"),
                                        "limits": r.get("limits"), "parallel": r.get("parallel"), "why": e.get("why", "")[:200]})
                if e.get("outcome") != "sampled" or r.get("result") is None:
                    out["problems"].append(f"{tree}-{name}-{rep}: {e.get('outcome')} {e.get('why', '')[:200]}"); continue
                S[tree].append(r["result"])
        out["jobs"][name] = info
        if len(S["baseline"]) != reps or len(S["gold"]) != reps: continue
        universe = set()
        for res in S["baseline"] + S["gold"]: universe |= set(res["cases"])
        dropped = sorted(universe & PERFORMANCE_CASES); universe -= PERFORMANCE_CASES
        for key in dropped:
            out["not_run_performance"].append({"job": name, "case": key, "present_in_samples": sum(key in res["cases"] for res in S["baseline"] + S["gold"])})
        def st(res, key):
            if key in res["cases"]: return res["cases"][key]
            return "fail" if case_file(key) in res["file_errors"] else "absent"
        counts = {k: 0 for k in ("f2p", "p2p", "excluded_fail_both", "unstable", "skipped", "broken_by_gold", "fixed_outside_commit_tests", "commit_tests_pass_both_out_of_scope")}
        for key in sorted(universe):
            b = [st(res, key) for res in S["baseline"]]; g = [st(res, key) for res in S["gold"]]
            in_commit = case_file(key) in commit_tests
            allb = lambda s: all(x == s for x in b); allg = lambda s: all(x == s for x in g)
            if allb("fail") and allg("pass"): kind = "f2p" if in_commit else "fixed_outside_commit_tests"
            elif allb("pass") and allg("pass"): kind = "p2p" if info["in_scope"] else "commit_tests_pass_both_out_of_scope"
            elif allb("fail") and allg("fail"): kind = "excluded_fail_both"
            elif allg("skip") and all(x in ("skip", "fail") for x in b): kind = "skipped"   # skipped with the fix (on baseline: skipped, or its file did not load)
            elif allb("pass") and allg("fail"): kind = "broken_by_gold"
            else: kind = "unstable"
            counts[kind] += 1
            entry = {"job": name, "case": key} if kind in ("f2p", "p2p") else {"job": name, "case": key, "baseline": b, "gold": g}
            out[kind].append(entry)
        info["counts"] = counts
        info["file_errors_baseline"] = sorted(set().union(*[set(r["file_errors"]) for r in S["baseline"]]))
        info["file_errors_gold"] = sorted(set().union(*[set(r["file_errors"]) for r in S["gold"]]))
        # failure text for the agent: baseline sample 1, blocks that belong to the commit's test files only
        # (a block starts at a "FAIL <file>::<case>" or "FILE <file>: ..." line and may hold blank lines: compiler output)
        keep = False
        for chunk in (S["baseline"][0].get("failure_text") or "").split("\n\n"):
            m = re.match(r"(FAIL|FILE) ([^:\n]+)", chunk.split("\n", 1)[0])
            if m:
                keep = m.group(2).strip() in commit_tests
                if keep: failure_blocks.append(chunk)
            elif keep: failure_blocks[-1] += "\n\n" + chunk
    out["counts"] = {k: len(out[k]) for k in ("f2p", "p2p", "excluded_fail_both", "unstable", "skipped", "broken_by_gold", "fixed_outside_commit_tests", "commit_tests_pass_both_out_of_scope")}
    out["usable"] = not out["problems"] and out["counts"]["f2p"] > 0
    if not out["counts"]["f2p"]: out["problems"].append("no F2P case: task flagged for replacement (criteria E1)")
    return out, "\n\n".join(failure_blocks)


def derive(tid, out_dir=None):
    out, failure = classify(tid)
    sm = secret_meta(tid)
    (ROOT / "secret" / tid / "cases.json").write_text(json.dumps(out))
    header = "Output of the task's test files on this snapshot (failing cases only; from the lab's own run, 3 of 3):\n\n"
    text = failure if len(failure) <= 8000 else "[... earlier failures trimmed ...]\n" + failure[-8000:]
    (ROOT / "cases" / tid / "failure.txt").write_text(header + text + "\n")
    if out_dir: (pathlib.Path(out_dir) / f"{tid}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({"id": tid, "usable": out["usable"], "counts": out["counts"], "problems": out["problems"][:8],
                      "jobs": {n: {"counts": j.get("counts"), "tool_s": [s["tool_s"] for s in j["samples"]]} for n, j in out["jobs"].items()}}), flush=True)
    return out


def main():
    a = sys.argv[1:]; mode = a[0]; tid = a[1]
    opt = lambda flag, default=None: a[a.index(flag) + 1] if flag in a else default
    os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    if mode == "repro":
        repro(tid, int(opt("--reps", "3")), int(opt("--parallel", "1")), tuple(opt("--trees", "baseline,gold").split(",")),
              set(opt("--jobs").split(",")) if opt("--jobs") else None, "--force" in a, set(opt("--kinds").split(",")) if opt("--kinds") else None)
    elif mode == "derive": derive(tid, opt("--out"))
    elif mode == "shell":
        r = sample(tid, a[2], {"name": "shell", "kind": "shell", "cmd": a[3], **({"cwd": opt("--cwd")} if opt("--cwd") else {})},
                   pod_name("sh", tid, a[2], "shell", int(time.time()) % 100000), cpu=opt("--cpu"), memory=opt("--memory"))
        tool = (r.get("result") or {}).get("tool") or {}
        print(tool.get("output", "")); print(tool.get("stderr", ""), file=sys.stderr)
        print("SHELL " + json.dumps({"executor": {k: v for k, v in r["executor"].items() if k != "tool"}, "rc": tool.get("rc"), "s": tool.get("s"), "pod": r["pod"]}))
    else: sys.exit("repro | derive | shell")


if __name__ == "__main__": main()
