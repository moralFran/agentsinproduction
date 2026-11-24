#!/usr/bin/env python3
"""Trusted host controller of the task preparation (experiment 05, A-v07). Runs ON aip-ctx-01 as the lab user.
Adapted from experiment 04's prep.py: only Git/file operations run here; dependency resolution (flutter pub get,
npm ci), which runs third-party install code, happens in a disposable Kata pod in ci-prep (cases/prep_worker.py).

Inputs (copied from the Mac, never from a git checkout of the app): ~/input/T<n>-parent.tar (git archive of the parent
commit), T<n>-tests.tar (the commit's test files as of the task commit), T<n>-fix.diff, T<n>-fix-source.diff,
T<n>-tests.diff, manifest.json, tasks.json.

  snapshot <T#>   /srv/ci/cases/<T#>/snapshot  = parent tree minus the exclusions of criteria E4, plus the commit's test
                  files, as a new Git repository with ONE commit (fixed author and date), no remote, no reflog;
                  /srv/ci/cases/<T#>/meta.json = public metadata for the agent (statement, areas, test commands);
                  /srv/ci/secret/<T#>/         = fix.diff (gabarito: source + config), fix-source.diff, tests.diff,
                                                 meta.json (jobs, file lists, commit ids). Never mounted in agent pods.
                  Prints the record (hashes, exclusion counts, leak audit) as one JSON line.
  deps <T#>       resolves the dependencies in a ci-prep pod and publishes them: the shared pub cache and node_modules
                  sets under /srv/ci/deps (read-only in every later pod), the per-task overlay (.dart_tool,
                  pubspec.lock) under /srv/ci/cases/<T#>/overlay, and the generated lock under /srv/ci/deps/locks.
"""
import hashlib, importlib.util, json, os, pathlib, re, shutil, subprocess, sys, tarfile, time

ROOT = pathlib.Path(os.environ.get("TEAM_ROOT", "/srv/ci")); INPUT = pathlib.Path(os.environ.get("TEAM_INPUT", os.path.expanduser("~/input")))
BOX_IMAGE = os.environ.get("BOX_IMAGE", "aip-team-box:1")
FB = "lib/internal/firebase"
# criteria.md E4 (+ the protocol's own list). A trailing "/" is a directory at that exact path; "**/name" matches the
# name at any depth; plain names are exact paths from the root.
EXCLUDE_EXACT = ["CLAUDE.md", "AGENTS.md", "perf_report.html", f"{FB}/.firebaserc"]
EXCLUDE_DIRS = ["docs", "gcp", "ops", "dev-env", "load-tests", ".github", ".vscode", ".firebase", ".superpowers",
                "scripts/security", "scripts/tests", "integration_test/tool"]
EXCLUDE_ANYWHERE = re.compile(r"(^|/)(google-services\.json|GoogleService-Info\.plist|CLAUDE\.md|AGENTS\.md)$|(^|/)\.firebase/|^\.gitleaks[^/]*$")
SNAPSHOT_DATE = "2026-11-15T00:00:00+00:00"


def command(args, cwd=None, env=None, timeout=1800):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout, env=env).stdout


def git(repo, *args, env=None):
    base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    base.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", **(env or {}))
    return command(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "core.autocrlf=false", *args], cwd=repo, env=base)


def excluded(path):
    if path in EXCLUDE_EXACT: return "exact"
    for d in EXCLUDE_DIRS:
        if path == d or path.startswith(d + "/"): return d + "/"
    if EXCLUDE_ANYWHERE.search(path): return "pattern"
    return None


def safe_members(tar):
    for m in tar.getmembers():
        p = pathlib.PurePosixPath(m.name)
        if p.is_absolute() or ".." in p.parts: raise ValueError(f"unsafe path in archive: {m.name}")
        if m.issym() or m.islnk():
            target = pathlib.PurePosixPath(m.linkname)
            if target.is_absolute() or ".." in (p.parent / target).parts: raise ValueError(f"link escapes the tree: {m.name}")
        if not (m.isfile() or m.isdir() or m.issym()): raise ValueError(f"unsupported member: {m.name}")
        yield m


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


FLUTTER_PROCS = 4          # `flutter test` processes side by side in the area-suite pod
FUNCTIONS_SHARDS = 3       # pods (each with its own emulators) the functions area suite is split over


def jobs_for(task, man, snap=None):
    """Test jobs of a task (criteria E1/E3). One job = one pod per sample.
    - "commit" jobs run the commit's test files (the only place an F2P case can be). They are small and run first in
      validation.
    - "area" jobs run the REST of an area's suite, and exist only when the commit has a source file in that area.
    in_scope says whether the job's area is touched by the commit's source: only then its pass/pass cases are P2P.
    The split changes no command: Flutter runs each test file in its own process either way, and the functions suite
    is one Jest process per file in the repository's own runner."""
    src, tests = man["source"], man["tests"]
    scope = {"flutter": any(p.endswith(".dart") for p in src),
             "functions": any(p.startswith(f"{FB}/functions/") for p in src),
             "rules": any(p.endswith(".rules") for p in src)}
    dart_tests = sorted(p for p in tests if p.endswith("_test.dart"))
    e2e_fn = sorted(p for p in tests if "/tests/e2e-functions/" in p)
    jest_tests = sorted(p for p in tests if p.endswith(".test.js") and p not in e2e_fn)
    relf = lambda p: os.path.relpath(p, f"{FB}/functions")
    is_rules = lambda p: "rules.test" in os.path.basename(p)
    jobs = []
    if dart_tests:
        jobs.append({"name": "flutter-commit", "kind": "flutter", "area": "flutter", "scope": "commit", "in_scope": scope["flutter"], "files": dart_tests})
    if jest_tests:
        # rules tests alone run as the CI job "Firestore Security Rules" does (project app-rules-test); anything else
        # as `make test-functions` does (project app-test). Both: emulators firestore, auth, storage.
        only_rules = all(is_rules(p) for p in jest_tests); project = "app-rules-test" if only_rules else "app-test"
        in_scope = (scope["rules"] if only_rules else scope["functions"] or (scope["rules"] and any(is_rules(p) for p in jest_tests)))
        jobs.append({"name": "jest-commit", "kind": "jest", "area": "rules" if only_rules else "functions", "scope": "commit", "in_scope": in_scope,
                     "project": project, "files": [relf(p) for p in jest_tests], "env": {"FIREBASE_RULES_TEST_PROJECT_ID": project}})
    if e2e_fn:
        jobs.append({"name": "e2e-functions-commit", "kind": "jest-e2e-functions", "area": "functions", "scope": "commit", "in_scope": scope["functions"],
                     "files": [relf(p) for p in e2e_fn]})
    if scope["flutter"]:
        jobs.append({"name": "flutter-area", "kind": "flutter", "area": "flutter", "scope": "area", "in_scope": True, "exclude": dart_tests, "procs": FLUTTER_PROCS})
    if scope["functions"]:
        # the repository's `npm test` (scripts/run-jest-shards.js): tests/*.test.js and tests/e2e/*.test.js, one Jest
        # process per file, under `firebase emulators:exec --project app-test --only firestore,auth,storage`. The rules
        # test files are part of tests/*.test.js, so these jobs also cover the rules area when both are in scope.
        for i in range(FUNCTIONS_SHARDS):
            jobs.append({"name": f"functions-area-{i + 1}", "kind": "jest", "area": "functions", "scope": "area", "in_scope": True, "project": "app-test",
                         "globs": ["tests/*.test.js", "tests/e2e/*.test.js"], "exclude": [relf(p) for p in jest_tests], "shard": [i, FUNCTIONS_SHARDS],
                         "env": {"FIREBASE_RULES_TEST_PROJECT_ID": "app-test"}})
    elif scope["rules"]:
        # CI job "Firestore Security Rules": `npm run test:rules` = every tests/*rules.test.js file, project app-rules-test
        jobs.append({"name": "rules-area", "kind": "jest", "area": "rules", "scope": "area", "in_scope": True, "project": "app-rules-test",
                     "globs": ["tests/*rules.test.js"], "exclude": [relf(p) for p in jest_tests], "env": {"FIREBASE_RULES_TEST_PROJECT_ID": "app-rules-test"}})
    return jobs, scope


def agent_commands(man):
    """The commit's test files as commands the agent can run from the repository root (same commands the jobs use)."""
    tests = man["tests"]; cmds = []
    dart = [p for p in tests if p.endswith("_test.dart")]
    e2e_fn = [p for p in tests if "/tests/e2e-functions/" in p]
    jest = [os.path.relpath(p, f"{FB}/functions") for p in tests if p.endswith(".test.js") and p not in e2e_fn]
    if dart: cmds.append("flutter test --no-pub --timeout=2m " + " ".join(dart))
    if jest:
        project = "app-rules-test" if all("rules.test" in p for p in jest) else "app-test"
        cmds.append(f"cd {FB} && FIREBASE_RULES_TEST_PROJECT_ID={project} firebase emulators:exec --project {project} --only firestore,auth,storage "
                    f"\"cd functions && NODE_OPTIONS=--experimental-vm-modules npx jest --runTestsByPath {' '.join(jest)} --runInBand --forceExit --watchman=false\"")
    return cmds


def snapshot(tid):
    man = json.load(open(INPUT / "manifest.json"))[tid]
    task = next(t for t in json.load(open(INPUT / "tasks.json")) if t["id"] == tid)
    case, secret = ROOT / "cases" / tid, ROOT / "secret" / tid
    if case.exists() or secret.exists(): raise ValueError("task already prepared; remove /srv/ci/cases/<id> and /srv/ci/secret/<id> explicitly")
    for name, info in man["files"].items():
        if sha256(INPUT / name) != info["sha256"]: raise ValueError(f"input {name} does not match the manifest")
    case.mkdir(parents=True); secret.mkdir(parents=True); secret.chmod(0o700)
    snap = case / "snapshot"; snap.mkdir()
    removed = {}
    with tarfile.open(INPUT / f"T{man['n']}-parent.tar") as tar:
        keep = []
        for m in safe_members(tar):
            why = excluded(m.name.rstrip("/"))
            if why:
                if m.isfile(): removed[why] = removed.get(why, 0) + 1
                continue
            keep.append(m)
        tar.extractall(snap, members=keep)
    with tarfile.open(INPUT / f"T{man['n']}-tests.tar") as tar:
        members = [m for m in safe_members(tar) if m.isfile()]
        if sorted(m.name for m in members) != sorted(man["tests"]): raise ValueError("tests archive does not match the manifest")
        if any(excluded(m.name) for m in members): raise ValueError("a commit test file sits in an excluded path")
        tar.extractall(snap, members=members)
    # empty directories left by the exclusions are not part of a Git tree anyway
    files_on_disk = sorted(str(p.relative_to(snap)) for p in snap.rglob("*") if p.is_file() or p.is_symlink())
    env = {"GIT_AUTHOR_NAME": "snapshot", "GIT_AUTHOR_EMAIL": "snapshot@example.invalid", "GIT_COMMITTER_NAME": "snapshot",
           "GIT_COMMITTER_EMAIL": "snapshot@example.invalid", "GIT_AUTHOR_DATE": SNAPSHOT_DATE, "GIT_COMMITTER_DATE": SNAPSHOT_DATE}
    git(snap, "init", "-q", "-b", "main")
    git(snap, "add", "-A", "-f", ".")                       # -f: the archive is the tree; .gitignore must not drop tracked files
    git(snap, "commit", "-q", "-m", "snapshot", env=env)
    tracked = sorted(git(snap, "ls-files", "-z").split("\0")[:-1])
    if tracked != files_on_disk: raise ValueError(f"snapshot commit does not hold the whole tree ({len(tracked)} tracked, {len(files_on_disk)} on disk)")
    shutil.rmtree(snap / ".git" / "logs", ignore_errors=True)
    for hook in (snap / ".git" / "hooks").glob("*"): hook.unlink()
    if git(snap, "remote").strip() or int(git(snap, "rev-list", "--count", "--all").strip()) != 1: raise ValueError("snapshot repository is not a single commit without remotes")
    if git(snap, "status", "--porcelain").strip(): raise ValueError("snapshot working tree is not clean")
    commit = git(snap, "rev-parse", "HEAD").strip(); tree = git(snap, "rev-parse", "HEAD^{tree}").strip()
    tar_sha = hashlib.sha256(subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=snap, check=True, capture_output=True).stdout).hexdigest()
    # secret side
    for name in ("fix.diff", "fix-source.diff", "tests.diff"):
        shutil.copyfile(INPUT / f"T{man['n']}-{name}", secret / name)
    jobs, areas_in_scope = jobs_for(task, man, snap)
    # the gabarito must apply to the snapshot (checked on a scratch copy of the index, nothing is written to the snapshot)
    for name in ("fix.diff", "fix-source.diff"):
        git(snap, "apply", "--check", "--binary", str(secret / name))
    # leak audit: identifiers of the fix, outside the commit's test files
    testset = set(man["tests"]); audit = []
    for leak in task.get("leak_ids", []):
        p = subprocess.run(["grep", "-rlF", "--exclude-dir=.git", "-e", leak["id"], "."], cwd=snap, capture_output=True, text=True)
        hits = sorted(h[2:] for h in p.stdout.splitlines()); outside = [h for h in hits if h not in testset]
        other_tests = [h for h in outside if re.search(r"(^|/)(tests?|integration_test)/", h)]
        audit.append({"id": leak["id"], "expected_in_parent": bool(leak.get("in_parent_outside_tests")), "in_commit_tests": [h for h in hits if h in testset],
                      "hits_outside_commit_tests": len(outside), "examples": outside[:6], "of_which_other_test_files": len(other_tests)})
    fix_only = [a["id"] for a in audit if not a["expected_in_parent"]]
    statement = task["statement"]
    statement_hits = [i for i in fix_only if i in statement]
    node_needed = any(j["kind"].startswith("jest") for j in jobs)
    meta = {"id": tid, "n": man["n"], "language": "Flutter/Dart and Node.js (Firebase: Cloud Functions, security rules)", "workdir": ".",
            "areas": task["areas"], "statement": statement, "test_files": man["tests"], "test_cmds": agent_commands(man),
            "snapshot_commit": commit}
    meta["test_cmd"] = "\n".join(meta["test_cmds"])
    (case / "meta.json").write_text(json.dumps(meta, indent=1))
    (case / "repo").mkdir()                                  # mount point of the disposable working copy
    record = {"id": tid, "n": man["n"], "commit": man["commit"], "parent": man["parent"], "snapshot_commit": commit, "snapshot_tree": tree,
              "snapshot_tar_sha256": tar_sha, "files": len(tracked), "excluded_files": removed, "tests_put_back": man["tests"],
              "source": man["source"], "config": man["config"], "docs_not_applied": man["docs"], "areas_in_scope": areas_in_scope,
              "jobs": jobs, "node_needed": node_needed, "leak_audit": audit,
              "leaks_fix_only_outside_tests": [a["id"] for a in audit if not a["expected_in_parent"] and a["hits_outside_commit_tests"]],
              "statement_names_fix_identifiers": statement_hits}
    (secret / "meta.json").write_text(json.dumps(record, indent=1))
    return record


# ----------------------------------------------------------------------------------------------------- dependencies
def dep_sets(snap):
    """Identity of the dependency sets (criteria E6): the pubspec without its version line; the npm lock files."""
    pub = re.sub(r"(?m)^version:.*\n", "", (snap / "pubspec.yaml").read_text())
    h = hashlib.sha256(pub.encode())
    for extra in sorted((snap / "vendor").rglob("pubspec.yaml")) if (snap / "vendor").is_dir() else []: h.update(extra.read_bytes())
    node = hashlib.sha256()
    for f in (f"{FB}/package.json", f"{FB}/package-lock.json", f"{FB}/functions/package.json", f"{FB}/functions/package-lock.json"):
        node.update(f.encode()); node.update((snap / f).read_bytes() if (snap / f).exists() else b"<absent>")
    return "pub-" + h.hexdigest()[:10], "node-" + node.hexdigest()[:10]


def worker_spec(tid, name, snap, out, pub_set, node_set, steps):
    spec = importlib.util.spec_from_file_location("netgate_pod", pathlib.Path(__file__).resolve().parent / "pod.py")
    pod = importlib.util.module_from_spec(spec); spec.loader.exec_module(pod)
    security = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
    gate = [pod.netgate_container(BOX_IMAGE, security, pod.PRIVATE_CANARIES)] if pod.netgate_enabled() else []
    case = f"/srv/ci/cases/{tid}"
    env = {"HOME": "/home/agent", "CASE_ID": tid, "PREP_STEPS": ",".join(steps), "PUB_SET": pub_set, "NODE_SET": node_set,
           "NPM_CONFIG_CACHE": "/tmp/npm-cache"}
    pins = pathlib.Path(__file__).resolve().parent.parent / "infra" / "locks" / "pins.json"      # {"package": "exact version"}
    if pins.exists(): env["PUB_PINS"] = json.dumps({k: v for k, v in json.load(open(pins)).items() if not k.startswith("_")})
    mounts = [{"name": "source", "mountPath": "/input", "readOnly": True}, {"name": "output", "mountPath": "/output"},
              {"name": "repo", "mountPath": f"{case}/repo"}, {"name": "tmp", "mountPath": "/tmp"},
              {"name": "code", "mountPath": "/code", "readOnly": True}, {"name": "deps", "mountPath": "/srv/ci/deps"}]
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "ci-prep"}, "spec": {
        **({"initContainers": gate} if gate else {}),
        "runtimeClassName": "kata-qemu", "automountServiceAccountToken": False, "enableServiceLinks": False,
        "restartPolicy": "Never", "activeDeadlineSeconds": 3000,
        "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{"name": "c", "image": BOX_IMAGE, "imagePullPolicy": "Never",
                        "command": ["python3", "-u", "/code/prep_worker.py"], "env": [{"name": k, "value": v} for k, v in env.items()],
                        "securityContext": security,
                        "resources": {"requests": {"cpu": "2", "memory": "4Gi"}, "limits": {"cpu": "6", "memory": "12Gi"}}, "volumeMounts": mounts}],
        "volumes": [{"name": "source", "hostPath": {"path": str(snap), "type": "Directory"}},
                    {"name": "output", "hostPath": {"path": str(out), "type": "Directory"}},
                    {"name": "deps", "hostPath": {"path": "/srv/ci/deps", "type": "Directory"}},
                    {"name": "repo", "emptyDir": {"sizeLimit": "12Gi"}}, {"name": "tmp", "emptyDir": {"sizeLimit": "12Gi"}},
                    {"name": "code", "configMap": {"name": "ci-prep-code"}}]}}


def deps(tid):
    case = ROOT / "cases" / tid; snap = case / "snapshot"; secret_meta = json.load(open(ROOT / "secret" / tid / "meta.json"))
    pub_set, node_set = dep_sets(snap)
    steps = ["pub"] + (["npm"] if secret_meta["node_needed"] and not (ROOT / "deps" / "node" / node_set / "DONE").exists() else [])
    work = ROOT / "work" / f"{tid}-deps"
    if work.exists(): subprocess.run(["sudo", "rm", "-rf", str(work)], check=True)
    work.mkdir(parents=True); work.chmod(0o777)
    for d in (ROOT / "deps", ROOT / "deps" / "pub-cache", ROOT / "deps" / "locks", ROOT / "deps" / "node"):
        d.mkdir(exist_ok=True); os.chmod(d, 0o777)
    name = f"prep-{tid.lower()}-deps"
    spec = worker_spec(tid, name, snap, work, pub_set, node_set, steps)
    kc = lambda *a: subprocess.run(["kubectl", "-n", "ci-prep", *a], capture_output=True, text=True)
    kc("delete", "pod", name, "--ignore-not-found", "--wait=true")
    r = subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(spec), text=True, capture_output=True)
    if r.returncode: raise ValueError(r.stderr)
    t0 = time.monotonic(); phase = ""
    while time.monotonic() - t0 < 3100:
        phase = kc("get", "pod", name, "-o", "jsonpath={.status.phase}").stdout
        if phase in ("Succeeded", "Failed"): break
        time.sleep(3)
    log = kc("logs", name).stdout; gate = kc("logs", name, "-c", "netgate").stdout
    (ROOT / "logs" / f"{name}.log").write_text(log)
    kc("delete", "pod", name, "--ignore-not-found", "--wait=true")
    if '"ok": false' in gate: raise ValueError("deps: infrastructure error, network gate: " + gate[-300:])
    if phase != "Succeeded" or "PREP_WORKER_DONE" not in log: raise ValueError("deps preparation failed: " + log[-1500:])
    # publish the per-task overlay (files the resolution created in the working copy; no node_modules, no app source)
    for target in (case / "overlay", case / "overlay.list"):
        if target.is_dir(): shutil.rmtree(target)
        elif target.exists(): target.unlink()
    if (work / "overlay").is_symlink(): raise ValueError("invalid overlay root")
    shutil.copytree(work / "overlay", case / "overlay", symlinks=True)
    shutil.copyfile(work / "overlay.list", case / "overlay.list")
    meta = json.load(open(case / "meta.json"))
    node_dir = ROOT / "deps" / "node" / node_set
    if secret_meta["node_needed"]:
        if not (node_dir / "DONE").exists(): raise ValueError("node_modules set was not published")
        # node_modules reach the working copy as two symlinks in the overlay, pointing at the read-only set mounted at
        # its own absolute path. (Mounting the set inside the working copy does not work: the kubelet creates the parent
        # directories of a nested mount as root, and the copy of the snapshot, uid 1000, then cannot write into them.)
        links = {f"{FB}/node_modules": node_dir / "node_modules"}
        if (node_dir / "functions" / "node_modules").is_dir(): links[f"{FB}/functions/node_modules"] = node_dir / "functions" / "node_modules"
        for rel, target in links.items():
            link = case / "overlay" / rel; link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists(): link.unlink()
            os.symlink(str(target), str(link))
        meta["node_dir"] = str(node_dir)
        # The functions' Jest configuration lists a project whose root (admin-scripts/dashboard) is git-ignored on the
        # owner's machine and absent from every tracked tree; Jest refuses to start when a root directory is missing
        # ("Directory ... in the roots[0] option was not found"), for any test file. Minimal handling: the overlay
        # carries that directory EMPTY (no file is added, Git does not see an empty directory).
        created = []
        try: projects = json.load(open(snap / FB / "functions" / "package.json")).get("jest", {}).get("projects", [])
        except (OSError, ValueError): projects = []
        for project in projects:
            for root in (project.get("roots") or []) if isinstance(project, dict) else []:
                rel = os.path.normpath(os.path.join(FB, "functions", root.replace("<rootDir>/", "").replace("<rootDir>", ".")))
                if rel.startswith("..") or (snap / rel).exists(): continue
                (case / "overlay" / rel).mkdir(parents=True, exist_ok=True); created.append(rel)
        meta["empty_dirs_for_jest_roots"] = created
    meta["dependency_sets"] = {"pub": pub_set, **({"node": node_set} if secret_meta["node_needed"] else {})}
    (case / "meta.json").write_text(json.dumps(meta, indent=1))
    lock = ROOT / "deps" / "locks" / pub_set / "pubspec.lock"
    done = [json.loads(l[len("PREP_STEP "):]) for l in log.splitlines() if l.startswith("PREP_STEP ")]
    subprocess.run(["sudo", "rm", "-rf", str(work)], check=True)
    return {"id": tid, "deps": "ok", "pub_set": pub_set, "node_set": node_set if secret_meta["node_needed"] else None, "steps": done,
            "pubspec_lock_sha256": sha256(lock), "empty_dirs_for_jest_roots": meta.get("empty_dirs_for_jest_roots"), "overlay_files": len((case / "overlay.list").read_text().splitlines()),
            "wall_s": round(time.monotonic() - t0, 1)}


def rejobs(tid):
    """Rewrites the job list in the secret metadata (after a change of jobs_for); the snapshot is not touched."""
    man = json.load(open(INPUT / "manifest.json"))[tid]; task = next(t for t in json.load(open(INPUT / "tasks.json")) if t["id"] == tid)
    f = ROOT / "secret" / tid / "meta.json"; record = json.load(open(f))
    record["jobs"], record["areas_in_scope"] = jobs_for(task, man)
    f.write_text(json.dumps(record, indent=1))
    return {"id": tid, "jobs": [j["name"] for j in record["jobs"]], "areas_in_scope": record["areas_in_scope"]}


def main():
    mode, tid = sys.argv[1], sys.argv[2]
    if os.getuid() == 0: sys.exit("run as the non-root lab user")
    os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    try: result = snapshot(tid) if mode == "snapshot" else deps(tid) if mode == "deps" else rejobs(tid) if mode == "jobs" else sys.exit("snapshot | deps | jobs")
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as e:
        detail = (getattr(e, "stderr", "") or "")[-400:]
        result = {"id": tid, mode: "fail", "why": (str(e) + " " + detail)[-1800:]}
    print(json.dumps(result), flush=True)


if __name__ == "__main__": main()
