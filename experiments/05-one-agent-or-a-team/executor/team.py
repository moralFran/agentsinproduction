#!/usr/bin/env python3
"""In-pod runner of experiment 05 (A-v07, one agent vs a team). Runs in a throw-away Kata pod in ci-exec: no network,
no credentials. One pod = one sample of one test JOB of one task, on one tree. Uses executor.py (same folder) for the
path rules (criteria E2), the Git reader and the tree-integrity check.

  prepare <baseline|gold|patch>   INIT container. Copies the snapshot and the dependency overlay into the working copy,
                                  then: baseline = nothing else (the snapshot already holds the commit's tests);
                                  gold = applies /in/fix.diff (the owner's fix, mounted here only);
                                  patch = checks /in/patch.diff against the path rules and applies it.
                                  Runs no app code. Writes /validation/prepared.json.
  run                             TEST container (no diff mounted). Reads the job from $JOB (JSON), runs it with the
                                  tree-integrity check around it, writes /out/result.json (per test CASE) and prints
                                  one line EXECUTOR <json summary>.

Job kinds (criteria E1/E3; commands are the repository's own, per file, with a machine-readable reporter):
  flutter   `flutter test --no-pub --timeout=2m --reporter json <files>` from the repo root. No --fail-fast. The files are
            the job's own list, or every test/**/*_test.dart minus job["exclude"]; job["procs"] runs that many
            `flutter test` processes side by side over a round-robin split of the list.
  jest      one `firebase emulators:exec --project P --only firestore,auth,storage` around one Jest process PER FILE
            (`jest --runTestsByPath F --runInBand --forceExit --watchman=false --json`, NODE_OPTIONS with
            --experimental-vm-modules, 300 s cap per file): what the repository's scripts/run-jest-shards.js does, minus
            its stop at the first failing file.
  jest-e2e-functions  the dedicated stack of `make test-e2e-functions`, pass 1 (gate ON): the environment is read from
            the run_pass body of the snapshot's own Makefile, nothing is copied into this harness.
  shell     a command, output kept (probes and offline proofs; classifies nothing).
A case key is "<file relative to the repo>::<full test name>". Statuses: pass, fail, skip. A file that could not be
loaded/run is listed in file_errors: every case of that file counts as failed in that sample."""
import glob, json, os, re, shlex, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import executor as ex

CASE = f"/srv/ci/cases/{os.environ.get('CASE_ID', '')}"
REPO = f"{CASE}/repo"
FB = "lib/internal/firebase"
JOBDIR = "/tmp/job"


def fresh():
    """Snapshot + overlay into the (empty, per-pod) working copy. No --delete: read-only node_modules are mounted inside."""
    subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    if os.path.isdir(f"{CASE}/overlay"):
        subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/overlay/", f"{REPO}/"], check=True)
    if os.path.exists(f"{CASE}/overlay.list"):
        with open(f"{REPO}/.git/info/exclude", "a") as x: x.write(open(f"{CASE}/overlay.list").read())


def prepare(tree):
    r = {"id": os.environ["CASE_ID"], "tree": tree}
    fresh()
    if tree == "baseline": r.update(outcome="applied", files=[])
    elif tree == "gold":
        p = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", "/in/fix.diff"], cwd=REPO, capture_output=True, text=True)
        r.update(outcome="applied" if p.returncode == 0 else "gold_did_not_apply", why=(p.stdout + p.stderr)[-300:], files=[])
    elif tree == "patch":
        if not open("/in/patch.diff").read().strip(): r.update(outcome="applied", files=[], empty_patch=True)
        else: r.update(ex.validate_patch("/in/patch.diff", REPO))
    else: raise SystemExit("prepare: baseline | gold | patch")
    with open("/validation/prepared.json", "w") as f: json.dump(r, f)
    print("PREPARED " + json.dumps(r), flush=True)


def run_to_files(cmd, cwd, env, timeout, stem):
    """Runs cmd with stdout/stderr to files (output can be tens of MB). Returns (rc, seconds); 124 on timeout."""
    t = time.monotonic()
    with open(f"{JOBDIR}/{stem}.out", "wb") as o, open(f"{JOBDIR}/{stem}.err", "wb") as e:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=o, stderr=e, start_new_session=True)
        try: rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            try: os.killpg(p.pid, signal.SIGTERM)
            except OSError: pass
            try: p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try: os.killpg(p.pid, signal.SIGKILL)
                except OSError: pass
            rc = 124
    return rc, time.monotonic() - t


def tail(path, n=4000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - n)); return f.read().decode("utf-8", "replace")
    except OSError: return ""


class Cases:
    def __init__(self): self.cases = {}; self.file_errors = {}; self.failures = []; self.files = {}
    def add(self, file, name, status):
        key = f"{file}::{name}"; n = 2
        while key in self.cases: key = f"{file}::{name} [#{n}]"; n += 1     # same name twice in one file: order of appearance
        self.cases[key] = status
        return key


def rel(path):
    path = path or ""
    if path.startswith("file://"): path = path[7:]
    for root in (os.path.realpath(REPO), REPO):
        if path.startswith(root + "/"): return path[len(root) + 1:]
    return path


# ---------------------------------------------------------------- flutter
# criteria E9 (owner, 2026-11-15): the app's performance tests are never executed, in any phase. The jobs never touched
# integration_test/ (perf journeys) or load-tests/ (k6; not even in the snapshot). One case inside the unit-test tree
# measures time on purpose (its own group is called "Timing group" [name redacted for the public copy] and it skips itself on CI as a
# "Performance test"): it is left out by name in every `flutter test` invocation of the harness. Full test names, exact.
NEVER_RUN_FLUTTER = ["Timing group timing case (name redacted)"]


def name_filter(names):
    """--name value for `flutter test`: a regular expression matching every full test name except the listed ones."""
    esc = lambda n: re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", n)
    return "^(?!(?:" + "|".join(esc(n) for n in names) + ")$)"


def flutter_files(job):
    """Explicit files, or every *_test.dart under test/ (what `flutter test` with no argument runs) minus job["exclude"]."""
    if job.get("files"): return list(job["files"])
    found = sorted(os.path.relpath(os.path.join(d, f), REPO) for d, _, fs in os.walk(os.path.join(REPO, "test")) for f in fs if f.endswith("_test.dart"))
    excl = set(job.get("exclude") or [])
    return [f for f in found if f not in excl]


def job_flutter(job, out):
    """job["procs"] > 1 splits the file list round-robin over that many `flutter test` processes running side by side
    in this pod. `flutter test` compiles the test files one after another through a single compiler process, so one
    process uses about one core; each file still runs in its own flutter_tester, exactly as in a single invocation."""
    import threading
    files = flutter_files(job); procs = max(1, min(int(job.get("procs", 1)), len(files) or 1))
    base = ["flutter", "test", "--no-pub", "--timeout=2m", "--reporter", "json"]
    if job.get("concurrency"): base += [f"--concurrency={int(job['concurrency'])}"]
    if NEVER_RUN_FLUTTER: base += ["--name", name_filter(NEVER_RUN_FLUTTER)]
    env = dict(os.environ); env.update(job.get("env") or {})
    chunks = [files[i::procs] for i in range(procs)]; results = [None] * procs
    def work(i):
        # Staggered start: every `flutter test` rewrites build/unit_test_assets when it starts (delete + write), before
        # it compiles anything. Eight seconds apart, the four rewrites never overlap and all end long before the first
        # test of any process runs (the first compile alone takes longer).
        time.sleep(i * float(job.get("stagger", 8)))
        results[i] = run_to_files(base + chunks[i], REPO, env, job.get("timeout", 3600), f"flutter-{i}")
    t0 = time.monotonic(); threads = [threading.Thread(target=work, args=(i,)) for i in range(procs)]
    [t.start() for t in threads]; [t.join() for t in threads]
    dt = time.monotonic() - t0
    for i in range(procs):
        suites, tests, done, errors = {}, {}, {}, {}
        with open(f"{JOBDIR}/flutter-{i}.out", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith("{"): continue
                try: e = json.loads(line)
                except ValueError: continue
                t = e.get("type")
                if t == "suite": suites[e["suite"]["id"]] = rel(e["suite"].get("path"))
                elif t == "testStart": tests[e["test"]["id"]] = e["test"]
                elif t == "testDone": done[e["testID"]] = e
                elif t == "error": errors.setdefault(e["testID"], []).append((e.get("error") or "") + "\n" + (e.get("stackTrace") or "")[:1500])
        for tid, test in tests.items():
            file = suites.get(test.get("suiteID"), "?"); d = done.get(tid); name = test.get("name") or ""
            hidden = bool(d and d.get("hidden")) or name.startswith("loading ")
            ok = bool(d) and d.get("result") == "success"
            if hidden:
                # "loading <file>" (compile/load) and (setUpAll)/(tearDownAll): not cases; a failure marks the whole file
                if not ok:
                    out.file_errors[file] = (name[:80].replace(REPO + "/", "") + ": " + (d or {}).get("result", "not finished"))
                    out.failures.append(f"FILE {file}: {name.replace(REPO + '/', '')}\n" + "\n".join(errors.get(tid, []))[:6000])
                continue
            status = "skip" if (d and d.get("skipped")) else "pass" if ok else "fail"
            key = out.add(file, name, status)
            if status == "fail": out.failures.append(f"FAIL {key}\n" + ("\n".join(errors.get(tid, [])) or "(no error event; test did not finish)")[:3000])
        seen = set(suites.values())
        for file in seen: out.files.setdefault(file, {})
        for file in chunks[i]:
            # a listed file that never produced a suite event (the process died or timed out before reaching it)
            if file not in seen: out.file_errors.setdefault(file, f"not run (flutter test process {i} rc={results[i][0]})")
    return {"rc": max(r[0] for r in results), "rcs": [r[0] for r in results], "s": round(dt, 1), "procs": procs, "files": len(files),
            "proc_s": [round(r[1], 1) for r in results], "stderr_tail": tail(f"{JOBDIR}/flutter-0.err", 1500)}


# ---------------------------------------------------------------- jest
INNER = r'''
import json, os, subprocess, sys, time
spec = json.load(open(sys.argv[1])); fdir = spec["functions_dir"]; status = {}
env = dict(os.environ)
if "--experimental-vm-modules" not in env.get("NODE_OPTIONS", ""):
    env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") + " --experimental-vm-modules").strip()
jest = None
for cand in (os.path.join(fdir, "node_modules/.bin/jest"), os.path.join(fdir, "../node_modules/.bin/jest")):
    if os.path.exists(cand): jest = [cand]; break
jest = jest or ["npx", "jest"]
for i, f in enumerate(spec["files"]):
    t = time.monotonic(); out = os.path.join(spec["dir"], f"{i}.json")
    cmd = jest + list(spec.get("jest_args", [])) + ["--runTestsByPath", f, "--runInBand", "--forceExit", "--watchman=false", "--json", "--outputFile", out]
    with open(os.path.join(spec["dir"], f"{i}.log"), "wb") as log:
        p = subprocess.Popen(cmd, cwd=fdir, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try: rc = p.wait(timeout=spec["file_timeout"])
        except subprocess.TimeoutExpired:
            import signal
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try: os.killpg(p.pid, sig)
                except OSError: pass
                try: p.wait(timeout=10); break
                except subprocess.TimeoutExpired: pass
            rc = 124
    status[f] = {"i": i, "rc": rc, "s": round(time.monotonic() - t, 1)}
    json.dump(status, open(os.path.join(spec["dir"], "status.json"), "w"))
    print(f"JESTFILE {i + 1}/{len(spec['files'])} rc={rc} {status[f]['s']}s {f}", flush=True)
'''


def jest_files(job):
    fdir = f"{REPO}/{FB}/functions"
    if job.get("files"): files = list(job["files"])
    else:
        files = []
        for g in job["globs"]: files += sorted(os.path.relpath(p, fdir) for p in glob.glob(os.path.join(fdir, g)))
        excl = set(job.get("exclude") or [])
        files = [f for f in files if f not in excl]
    if job.get("shard"):
        i, k = job["shard"]; files = files[i::k]
    return fdir, files


def collect_jest(job, out, fdir, files):
    jd = f"{JOBDIR}/jest"
    try: status = json.load(open(f"{jd}/status.json"))
    except (OSError, ValueError): status = {}
    for i, f in enumerate(files):
        file = os.path.relpath(os.path.join(fdir, f), REPO); st = status.get(f)
        out.files[file] = {"rc": st["rc"], "s": st["s"]} if st else {"rc": None, "s": None}
        try: data = json.load(open(f"{jd}/{i}.json"))
        except (OSError, ValueError): data = None
        if st is None: out.file_errors[file] = "not run (the job ended before this file)"; continue
        if st["rc"] == 124: out.file_errors[file] = "timeout"
        results = (data or {}).get("testResults") or []
        if data is None or not results:
            out.file_errors.setdefault(file, f"no Jest result (rc={st['rc']})")
            out.failures.append(f"FILE {file}: {out.file_errors[file]}\n" + tail(f"{jd}/{i}.log", 3000)); continue
        for res in results:
            asserts = res.get("assertionResults") or []
            if not asserts and res.get("status") == "failed":
                out.file_errors.setdefault(file, "test file failed to run")
                out.failures.append(f"FILE {file}: failed to run\n" + (res.get("message") or "")[:6000]); continue
            failed = False
            for a in asserts:
                s = a.get("status"); status_ = "pass" if s == "passed" else "fail" if s == "failed" else "skip"
                key = out.add(file, a.get("fullName") or " ".join((a.get("ancestorTitles") or []) + [a.get("title") or ""]), status_)
                if status_ == "fail":
                    failed = True
                    out.failures.append(f"FAIL {key}\n" + "\n".join(a.get("failureMessages") or [])[:3000])
            if res.get("status") == "failed" and not failed and file not in out.file_errors:
                # e.g. an afterAll hook threw: cases are reported, the file is red. Kept as information, not a file error.
                out.files[file]["file_status"] = "failed_without_failed_case"


def job_jest(job, out):
    fdir, files = jest_files(job)
    os.makedirs(f"{JOBDIR}/jest", exist_ok=True)
    json.dump({"functions_dir": fdir, "files": files, "dir": f"{JOBDIR}/jest", "file_timeout": job.get("file_timeout", 300),
               "jest_args": job.get("jest_args", [])}, open(f"{JOBDIR}/inner.json", "w"))
    open(f"{JOBDIR}/inner.py", "w").write(INNER)
    env = dict(os.environ); env.update(job.get("env") or {})
    cmd = ["firebase", "emulators:exec", "--project", job.get("project", "app-test"), "--only", job.get("only", "firestore,auth,storage"),
           f"python3 {JOBDIR}/inner.py {JOBDIR}/inner.json"]
    rc, dt = run_to_files(cmd, f"{REPO}/{FB}", env, job.get("timeout", 5400), "emulators")
    collect_jest(job, out, fdir, files)
    return {"rc": rc, "s": round(dt, 1), "emulators_tail": tail(f"{JOBDIR}/emulators.out", 2500) + tail(f"{JOBDIR}/emulators.err", 800)}


def makefile_run_pass_env():
    """NAME=VALUE lines of the run_pass() body of the test-e2e-functions target, as written in the snapshot's Makefile."""
    text = open(f"{REPO}/Makefile", encoding="utf-8").read()
    start = text.index("test-e2e-functions:"); body = text[text.index("run_pass() {", start):]
    body = body[:body.index("firebase emulators:exec")]
    pepper = re.search(r"^E2E_TEST_PEPPER\s*\?=\s*(.+)$", text, re.M)
    env = {}
    for m in re.finditer(r"^\s*([A-Z][A-Z0-9_]*)=(\"[^\"]*\"|\S+)\s*\\$", body, re.M):
        v = m.group(2).strip('"')
        env[m.group(1)] = v.replace("$(E2E_TEST_PEPPER)", pepper.group(1).strip() if pepper else "")
    return env


def job_jest_e2e_functions(job, out):
    fdir, files = jest_files(job)
    e2edir = f"{fdir}/tests/e2e-functions"; project = job.get("project", "demo-app-e2e-fn"); log = f"{JOBDIR}/netguard-on.jsonl"
    open(log, "w").close()
    stub = subprocess.run(["node", f"{e2edir}/cpf-hub-stub.fixture.js"], capture_output=True, text=True, cwd=f"{REPO}/{FB}")
    subst = {"$$log": log, "$$pass": "on", "$$project": project, "$$e2edir": e2edir, "$$gate": "true", "$$cpf_hub_stub": stub.stdout.strip()}
    env = dict(os.environ)
    for k, v in makefile_run_pass_env().items():
        for a, b in subst.items(): v = v.replace(a, b)
        env[k] = v
    env.update(job.get("env") or {})
    dotenv = f"{fdir}/.env.{project}"; created = False
    if not os.path.exists(dotenv) and os.path.exists(f"{e2edir}/default-gates.fixture"):
        open(dotenv, "wb").write(open(f"{e2edir}/default-gates.fixture", "rb").read()); created = True
    os.makedirs(f"{JOBDIR}/jest", exist_ok=True)
    json.dump({"functions_dir": fdir, "files": files, "dir": f"{JOBDIR}/jest", "file_timeout": job.get("file_timeout", 900),
               "jest_args": ["--config", job.get("config", "tests/e2e-functions/jest.config.js")]}, open(f"{JOBDIR}/inner.json", "w"))
    open(f"{JOBDIR}/inner.py", "w").write(INNER)
    cmd = ["firebase", "emulators:exec", "--project", project, "--config", "firebase.e2e-functions.json", "--only", "auth,firestore,functions,storage",
           f"python3 {JOBDIR}/inner.py {JOBDIR}/inner.json"]
    try: rc, dt = run_to_files(cmd, f"{REPO}/{FB}", env, job.get("timeout", 3600), "emulators")
    finally:
        if created and os.path.exists(dotenv): os.remove(dotenv)
    collect_jest(job, out, fdir, files)
    ng = subprocess.run(["node", f"{e2edir}/verify-netguard.js", log, "on"], capture_output=True, text=True, cwd=f"{REPO}/{FB}") if os.path.exists(f"{e2edir}/verify-netguard.js") else None
    return {"rc": rc, "s": round(dt, 1), "netguard_rc": ng.returncode if ng else None, "netguard_tail": ((ng.stdout + ng.stderr)[-400:] if ng else ""),
            "emulators_tail": tail(f"{JOBDIR}/emulators.out", 2500) + tail(f"{JOBDIR}/emulators.err", 800)}


def job_shell(job, out):
    env = dict(os.environ); env.update(job.get("env") or {})
    rc, dt = run_to_files(["bash", "-o", "pipefail", "-c", job["cmd"]], os.path.join(REPO, job.get("cwd", ".")), env, job.get("timeout", 1800), "shell")
    return {"rc": rc, "s": round(dt, 1), "output": tail(f"{JOBDIR}/shell.out", 60000), "stderr": tail(f"{JOBDIR}/shell.err", 8000)}


KINDS = {"flutter": job_flutter, "jest": job_jest, "jest-e2e-functions": job_jest_e2e_functions, "shell": job_shell}


def run():
    prepared = json.load(open("/validation/prepared.json"))
    job = json.loads(os.environ["JOB"])
    r = {"id": prepared["id"], "tree": prepared["tree"], "job": job.get("name"), "kind": job.get("kind"), "prepared": prepared.get("outcome"),
         "files": prepared.get("files", []), **({"empty_patch": True} if prepared.get("empty_patch") else {})}
    if prepared.get("outcome") != "applied":
        r.update(outcome=prepared.get("outcome"), why=prepared.get("why", "")); print("EXECUTOR " + json.dumps(r), flush=True); return
    os.makedirs(JOBDIR, exist_ok=True); out = Cases(); detail = {}
    try:
        ex.checker_git(["update-index", "-q", "--refresh"], REPO)
        before = ex.tree_state(REPO)
        tool = KINDS[job["kind"]](job, out)
        after = ex.tree_state(REPO, baseline=before)
        if before != after:
            paths = sorted(ex.changed_by(before[0], after[0]) | ex.changed_by(before[1], after[1]))
            r.update(outcome="test_changed_tree", why="test command changed the working tree: " + ", ".join(paths[:8]))
        else: r.update(outcome="sampled")
    except (ValueError, OSError, KeyError) as e:
        tool = {}; r.update(outcome="infra_error", why=f"{type(e).__name__}: {e}"[:400])
    counts = {s: sum(v == s for v in out.cases.values()) for s in ("pass", "fail", "skip")}
    r.update(tool=tool if job.get("kind") != "shell" else {k: tool.get(k) for k in ("rc", "s")}, counts=counts, file_errors=len(out.file_errors))
    detail = {**r, "tool": tool, "cases": out.cases, "file_errors": out.file_errors, "file_times": out.files, "failure_text": "\n\n".join(out.failures)[-200000:]}
    if os.path.isdir("/out"):
        with open("/out/result.json.tmp", "w") as f: json.dump(detail, f)
        os.replace("/out/result.json.tmp", "/out/result.json")
    print("EXECUTOR " + json.dumps(r), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "prepare": prepare(sys.argv[2])
    elif sys.argv[1] == "run": run()
    else: raise SystemExit("usage: team.py prepare <baseline|gold|patch> | run")
