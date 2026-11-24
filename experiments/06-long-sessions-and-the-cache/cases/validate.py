#!/usr/bin/env python3
"""Validator entry point for attempts and controls (experiment 05, criteria E2 and E10). Trusted host side; runs ON aip-ctx-01.
usage: validate.py <T#> <patch.diff> [--prefix NAME] [--parallel P] [--reps 3] [--all] [--save FILE]

 1. Path rules, on the host and again in every pod's init container (executor.validate_patch): the patch is rejected if
    it does not apply or touches a test file, CI or configuration (pubspec.yaml, package.json, lock files, firebase*.json,
    analysis_options.yaml, .github/, Makefile, ...). The host check runs `git apply` on a scratch copy of the snapshot; no
    app code is executed on the host.
 2. Stage 1 (criteria E10): the commit jobs (the commit's test files), `reps` samples each, every one a fresh
    no-network Kata pod whose init container copies the snapshot, applies the patch and runs nothing; the test container
    mounts no diff and no secret directory. Every F2P case and every P2P case of those files must pass in all samples;
    otherwise the verdict is `not_resolved` and stage 2 does not run (`--all` runs it anyway, for information; the
    verdict stays `not_resolved`). An empty patch is run as it is: the control that must fail here.
 3. Stage 2: one sample of each area job. Every test file with a P2P case that did not pass (or that failed to load)
    is rerun twice, that file only. Broken = fails in the first sample and in at least one rerun => `not_resolved`.
    Passes both reruns = `unstable_in_attempt`: listed, not counted against the patch.
 4. Integrity as in experiment 04: a sample whose tests changed the working tree is `test_changed_tree`; a missing
    result, a failed network gate or a dead pod is `infra_error`; a deadline is `timeout`. None of these is a verdict
    about the patch.
 5. The record says which stage decided (`decided_in_stage`: 0 path rules, 1, 2) and lists `broken` and
    `unstable_in_attempt`.
Prints one line: VERDICT <json>. The F2P/P2P lists are /srv/ci/secret/<T#>/cases.json (written by team_host.py derive;
frozen by the main session before the collection)."""
import os, sys
# cases/ still holds experiment 04's queue.py, which would shadow the standard library's `queue` (needed by
# concurrent.futures) because a script's own directory comes first on sys.path. Drop that entry before importing.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]
import concurrent.futures, importlib.util, json, pathlib, shutil, subprocess, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
host = _load("team_host", HERE / "team_host.py")
ex = _load("executor", HERE.parent / "executor" / "executor.py")
ROOT = pathlib.Path(os.environ.get("TEAM_ROOT", "/srv/ci"))          # TEAM_ROOT: local tests only


def host_patch_check(tid, patch):
    """Same rules as the pod's init container, on a scratch copy of the snapshot. Returns the executor's record."""
    if not pathlib.Path(patch).read_text(errors="replace").strip(): return {"outcome": "applied", "files": [], "empty_patch": True}
    tmp = tempfile.mkdtemp(prefix="vp-", dir=str(ROOT / "work"))
    try:
        subprocess.run(["rsync", "-a", f"{ROOT}/cases/{tid}/snapshot/", tmp + "/"], check=True)
        return ex.validate_patch(os.path.abspath(patch), tmp)
    finally: shutil.rmtree(tmp, ignore_errors=True)


FB_FUNCTIONS = "lib/internal/firebase/functions"
INTEGRITY = ("test_changed_tree", "timeout", "rejected_by_validator", "did_not_apply")


def rerun_job(job, files):
    """The same job restricted to some of its test files (stage 2 reruns): same kind, project and environment, the files
    given explicitly. Flutter runs each file in its own process and Jest gets one process per file, as in the suite."""
    r = {"name": job["name"] + "-rr", "kind": job["kind"], "area": job["area"], "scope": "rerun", "in_scope": True}
    for k in ("project", "env", "only", "file_timeout"):
        if k in job: r[k] = job[k]
    if job["kind"] == "flutter": r.update(files=sorted(files), procs=1 if len(files) <= 8 else int(job.get("procs", 1)))
    else: r["files"] = sorted(os.path.relpath(f, FB_FUNCTIONS) for f in files)
    return r


def dirty_files(res):
    """{file: why} for the files of one sample that did not end clean (criteria E22): the executor's file errors, a
    file whose process timed out (rc 124), and a Jest file that is red although none of its cases failed.
    Contract with executor/team.py (the `detail` it writes to /out/result.json): `file_errors` = {test file: why} and
    `file_times` = {test file: {rc, s, file_status}}. `files` in that record is the LIST of files the patch touches,
    not test files (the first version of this function read it by mistake). A record without a dict in either field
    is not a result this function can read: it raises, and the sample ends the validation as infra_error."""
    fe, ft = res.get("file_errors"), res.get("file_times")
    if not isinstance(fe, dict) or not isinstance(ft, dict): raise ValueError("result without file_errors/file_times dicts")
    out = {f: str(why)[:120] for f, why in fe.items()}
    for f, st in ft.items():
        if not isinstance(st, dict) or f in out: continue
        if st.get("rc") == 124: out[f] = "timeout"
        elif st.get("file_status") == "failed_without_failed_case": out[f] = "file red without a failed case"
    return out


def validate_task(tid, patch, prefix="v", parallel=1, reps=3, run_all=False, runner=None):
    """criteria E10 (owner, 2026-11-15), for attempts and for the controls.
    Stage 0: path rules. Stage 1: the commit jobs, `reps` samples each; every F2P case and every P2P case of those
    files must pass in all of them, else not_resolved and stage 2 does not run. Stage 2: ONE sample of each area job;
    every test file with a P2P case that did not pass (a file that failed to load counts as all its cases failing) is
    rerun twice, that file only; a case that passes both reruns is unstable_in_attempt (reported, not counted against
    the patch). criteria E18 (2026-11-16): a case that failed again is compared with the owner's fix at the same time
    (its file once on the gold tree): failing there too = environment_dependent (reported, not counted); passing there,
    it runs once more with the patch and is BROKEN only if it fails again. Any broken case => not_resolved. A sample that is not a result (dead pod, failed gate, deadline, tests changed the tree) ends the
    validation with that outcome, never with a verdict about the patch."""
    t0 = time.time(); runner = runner or host.sample
    lists = json.load(open(ROOT / "secret" / tid / "cases.json")); sm = host.secret_meta(tid)
    need = {}
    for kind in ("f2p", "p2p"):
        for e in lists[kind]:
            if e["case"] in host.PERFORMANCE_CASES: continue                     # criteria E9: never run, never required
            need.setdefault(e["job"], {"f2p": [], "p2p": []})[kind].append(e["case"])
    v = {"id": tid, "mode": "validate", "rule": "E10 two stages + E18 control at the same time + E22 dirty files + E23 killed file", "snapshot_commit": sm["snapshot_commit"],
         "f2p_total": sum(len(n["f2p"]) for n in need.values()), "p2p_total": sum(len(n["p2p"]) for n in need.values()),
         "reps": reps, "decided_in_stage": None, "stage1": None, "stage2": None, "broken": [], "unstable_in_attempt": [],
         "environment_dependent": [], "samples": []}
    def done(outcome, stage, **kw):
        v.update(outcome=outcome, decided_in_stage=stage, wall_s=round(time.time() - t0, 1), **kw); return v
    if not v["f2p_total"]: return done("infra_error", 0, why="the task has no F2P case")
    check = host_patch_check(tid, patch); v["files"] = check.get("files", [])
    if check.get("empty_patch"): v["empty_patch"] = True
    if check["outcome"] != "applied": return done(check["outcome"], 0, why=check.get("why", ""))
    stage1 = [j for j in sm["jobs"] if j["scope"] == "commit" and j["name"] in need]
    stage2 = [j for j in sm["jobs"] if j["scope"] != "commit" and j["name"] in need]
    if any(need[j["name"]]["f2p"] for j in stage2): return done("infra_error", 0, why="an F2P case is listed under an area job")
    orphan = sorted(set(need) - {j["name"] for j in stage1 + stage2})    # every job that holds a required case must run
    if orphan: return done("infra_error", 0, why=f"required cases listed under job(s) that are not in the task's jobs: {orphan}")

    def one(item):
        stage, job, label, wanted = item[:4]; tree = item[4] if len(item) > 4 else "patch"
        r = runner(tid, tree, job, host.pod_name(prefix, tid, tree, job["name"], label), **({"patch": patch} if tree == "patch" else {}))
        e = r["executor"]; res = r.get("result") or {}
        s = {"stage": stage, "job": job["name"], "sample": label, "tree": tree, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "outcome": e.get("outcome"), "tool_s": (e.get("tool") or {}).get("s"),
             "pod_wall_s": r["pod"].get("wall_s"), "limits": r.get("limits"), "counts": e.get("counts"), "why": e.get("why", "")[:200]}
        ok = e.get("outcome") == "sampled" and r.get("result") is not None
        if ok:
            try: dirty = dirty_files(res)
            except ValueError as err: ok = False; s.update(outcome="infra_error", why=f"unreadable sample result: {err}")
        if ok:
            # criteria E23 (Francisco, 2026-11-16): a test file that holds a required case and was killed by the per-file
            # limit (rc 124) before reporting ANY case is not a result about the patch. The sample ends the validation as
            # `timeout`, which criteria E16 redoes once on the same saved patch; a second timeout counts as no fix. A killed
            # file without required cases changes nothing (no verdict reads it).
            req = {host.case_file(c) for kind in ("f2p", "p2p") for c in wanted.get(kind, [])}
            killed = sorted(f for f, st in res["file_times"].items()
                            if f in req and isinstance(st, dict) and st.get("rc") == 124 and not any(c.startswith(f + "::") for c in (res.get("cases") or {})))
            if killed: ok = False; s.update(outcome="timeout", why=f"E23: killed by the per-file limit before reporting any case: {killed[:5]}")
        cases = (res.get("cases") or {}) if ok else {}
        # a case passes only if it is reported as "pass": absent, skipped, failed, or its file did not load => not passed.
        # criteria E22 (2026-11-16, after an external review): and only if its FILE ended clean in this sample. A file
        # with a file error (did not load, setUpAll/tearDownAll failed, timed out, did not run) or a Jest file that is
        # red without a failed case (e.g. afterAll threw) is dirty: every required case in it counts as not passed,
        # whatever the case entry says. The same reading applies to the gold tree in the E18 control, so a file that
        # is dirty with the owner's fix too ends as environment_dependent and does not count against the patch.
        notpass = {kind: [c for c in wanted.get(kind, []) if cases.get(c) != "pass" or host.case_file(c) in dirty] for kind in ("f2p", "p2p")} if ok else {}
        if ok:
            hit = sorted({host.case_file(c) for kind in ("f2p", "p2p") for c in wanted.get(kind, []) if host.case_file(c) in dirty})
            s.update(f2p_failed=len(notpass["f2p"]), p2p_failed=len(notpass["p2p"]), file_errors=len(res.get("file_errors") or {}),
                     dirty_files=len(dirty), dirty_files_with_required_cases={f: dirty[f] for f in hit[:40]})
        return s, ok, notpass

    def batch(items):
        t = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, parallel)) as pool: out = list(pool.map(one, items))
        v["samples"] += [s for s, _, _ in out]
        bad = [s for s, ok, _ in out if not ok]
        return out, bad, round(time.time() - t, 1)

    def not_a_result(bad, stage):
        o = bad[0]["outcome"]
        return done(o if o in INTEGRITY else "infra_error", stage, why=f"{bad[0]['job']} {bad[0]['sample']}: {bad[0]['why']}")

    # ---- stage 1: the commit's test files, `reps` samples
    out, bad, wall = batch([(1, j, rep, need[j["name"]]) for rep in range(1, reps + 1) for j in stage1])
    if bad: return not_a_result(bad, 1)
    fails = {"f2p": {}, "p2p": {}}
    for s, _, notpass in out:
        for kind in ("f2p", "p2p"):
            for c in notpass[kind]: fails[kind].setdefault(c, []).append(s["sample"])
    v["stage1"] = {"jobs": [j["name"] for j in stage1], "samples": len(out), "wall_s": wall,
                   "f2p_failed": len(fails["f2p"]), "p2p_failed": len(fails["p2p"]),
                   "failed_examples": [{"kind": k, "case": c, "failed_in_samples": r} for k in ("f2p", "p2p") for c, r in sorted(fails[k].items())[:10]]}
    v["f2p_failed"] = len(fails["f2p"]); v["p2p_failed_stage1"] = len(fails["p2p"])
    stage1_failed = bool(fails["f2p"] or fails["p2p"])
    if stage1_failed and not run_all: return done("not_resolved", 1)

    # ---- stage 2: one sample of each area suite, then two reruns of the files that hold a P2P case that did not pass
    out, bad, wall = batch([(2, j, "s2", need[j["name"]]) for j in stage2])
    if bad: return not_a_result(bad, 2)
    v["stage2"] = {"jobs": [j["name"] for j in stage2], "first_samples": len(out), "first_wall_s": wall, "files_rerun": {}, "rerun_samples": 0, "rerun_wall_s": 0.0}
    first_fail = {j["name"]: notpass["p2p"] for j, (_, _, notpass) in zip(stage2, out) if notpass["p2p"]}
    reruns = []
    for j in stage2:
        failed = first_fail.get(j["name"])
        if not failed: continue
        files = sorted({host.case_file(c) for c in failed}); v["stage2"]["files_rerun"][j["name"]] = files
        rj = rerun_job(j, files)
        reruns += [(2, rj, n, {"p2p": failed}) for n in (1, 2)]
    if reruns:
        out, bad, wall = batch(reruns)
        v["stage2"].update(rerun_samples=len(out), rerun_wall_s=wall)
        if bad: return not_a_result(bad, 2)
        failed_again = {}
        for s, _, notpass in out:
            for c in notpass["p2p"]: failed_again.setdefault(c, []).append(s["sample"])
        for name, failed in first_fail.items():
            for c in sorted(failed):
                if c not in failed_again: v["unstable_in_attempt"].append({"job": name, "case": c})
        # ---- criteria E18, the control at the same time: the files of the cases that failed again run ONCE on the owner's
        # tree (the task's own fix, no patch). A case that does not pass there either depends on the box or on the clock,
        # not on the patch: it is reported as environment_dependent and does not count. A case that passes there is run
        # once more with the patch (sample 3, after the control): failing again = BROKEN, passing = unstable_in_attempt.
        jobs = {j["name"]: j for j in stage2}
        again = {name: sorted(c for c in failed if c in failed_again) for name, failed in first_fail.items()}
        again = {name: cs for name, cs in again.items() if cs}
        if again:
            out, bad, wall = batch([(2, {**rerun_job(jobs[name], {host.case_file(c) for c in cs}), "name": name + "-ck"}, "g1", {"p2p": cs}, "gold")
                                    for name, cs in again.items()])
            v["stage2"].update(control_samples=len(out), control_wall_s=wall)
            if bad: return not_a_result(bad, 2)
            env = {c for _, _, notpass in out for c in notpass["p2p"]}
            confirm = {name: [c for c in cs if c not in env] for name, cs in again.items()}
            confirm = {name: cs for name, cs in confirm.items() if cs}
            failed_3 = set()
            if confirm:
                out, bad, wall3 = batch([(2, rerun_job(jobs[name], {host.case_file(c) for c in cs}), 3, {"p2p": cs}) for name, cs in confirm.items()])
                v["stage2"].update(rerun_samples=v["stage2"]["rerun_samples"] + len(out), rerun_wall_s=round(v["stage2"]["rerun_wall_s"] + wall3, 1))
                if bad: return not_a_result(bad, 2)
                failed_3 = {c for _, _, notpass in out for c in notpass["p2p"]}
            for name, cs in again.items():
                for c in cs:
                    rec = {"job": name, "case": c, "failed_in_reruns": failed_again[c]}
                    if c in env: v["environment_dependent"].append({**rec, "why": "does not pass with the owner's fix at the same time either"})
                    elif c in failed_3: v["broken"].append({**rec, "passes_with_owner_fix_now": True, "failed_after_control": True})
                    else: v["unstable_in_attempt"].append({**rec, "passes_with_owner_fix_now": True, "failed_after_control": False})
    v["stage2"]["wall_s"] = round(v["stage2"]["first_wall_s"] + v["stage2"]["rerun_wall_s"] + v["stage2"].get("control_wall_s", 0.0), 1)
    v["stage2"]["broken"] = len(v["broken"]); v["stage2"]["unstable_in_attempt"] = len(v["unstable_in_attempt"])
    v["stage2"]["environment_dependent"] = len(v["environment_dependent"])
    if stage1_failed: return done("not_resolved", 1)                    # only with run_all: stage 2 was informative
    return done("not_resolved" if v["broken"] else "resolved", 2)


def main():
    a = sys.argv[1:]; tid, patch = a[0], a[1]
    opt = lambda flag, default=None: a[a.index(flag) + 1] if flag in a else default
    os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    # experiment 04's callers passed the pod-name prefix as a third positional argument: still accepted
    prefix = opt("--prefix", a[2] if len(a) > 2 and not a[2].startswith("--") else "v")
    v = validate_task(tid, patch, prefix, int(opt("--parallel", "1")), int(opt("--reps", "3")), "--all" in a)
    if opt("--save"): pathlib.Path(opt("--save")).write_text(json.dumps(v, indent=1))
    print("VERDICT " + json.dumps(v), flush=True)
    print("EXECUTOR " + json.dumps(v), flush=True)           # same record under the tag cases/attempt.sh reads


if __name__ == "__main__": main()
