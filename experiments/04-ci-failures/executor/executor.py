#!/usr/bin/env python3
"""Executor: runs in a throw-away Kata pod with NO network and NO credentials. Mounts (read-only):
the case snapshot and offline dependencies at their prepared paths. Validation init containers apply the agent patch
and (for hidden tests) /in/hidden.diff without running case code. The test container receives no input diffs.
/in/fix.diff is for repro fixed only. The working copy goes to an empty dir at the path the case was prepared for.
  repro <broken|fixed> <N>   run the case's test command N times on the broken tree, or on broken + maintainer's fix
  validate <suite|hidden>     one fresh-pod sample, aggregated 3/3 by cases/validate.py (post-collection):
                               (a) it applies; (b) it touches no test, CI, lint/test configuration, dependency or lock
                               file; (c) the original test command passes 3/3; (d) with the maintainer's test-file changes
                               added on top, the hidden test command passes 3/3 (when the fix had test changes).
Prints one line EXECUTOR <json>.
Harness fixes of 2026-11-12, made AFTER the v1/v2 collection and the post-collection audit (nothing recorded was re-run):
  - the changed paths come from Git itself, NUL-separated (`git apply --numstat -z` on the patch, plus `git status -z`
    before and after applying it); any error reading them rejects the patch. The old header regex missed paths with a
    space (a test file such as `tests/has space.py` passed check (b) unseen);
  - FORBIDDEN matches everything UNDER CI directories (.github/, .circleci/, ...), not only the directory name itself;
  - `run` (audit mode) stops before the command when a patch or the maintainer's test changes do not apply.
Offline test: executor/test_executor.py (synthetic repository, no case code)."""
import hashlib, json, os, re, shutil, stat, subprocess, sys, time

RUN_TIMEOUT = 600
# test files, including test EXPECTATIONS: snapshot files (__snapshots__/, *.snap) and golden files (*.golden, golden/).
# The first version missed snapshots; found by the smoke test on 11/11 (google/osv-scanner: fix and patch were only a .snap)
TESTFILE = re.compile(r"(^|/)(tests?|testdata|testing|__snapshots__|golden|fixtures)(/|$)|_test\.go$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|\.snap$|\.golden$")   # fixtures/ added 12/11 (audit; future runs only)
# CI, dependency, lint/test configuration. Directories match themselves AND everything under them; until 2026-11-12 (after
# the collection) .github and .circleci sat in the file list, anchored with $, so .github/workflows/ci.yml did not match.
# The CI names after .circleci (.gitlab/, .buildkite/, .woodpecker/, .drone.yml, azure-pipelines, appveyor, Jenkinsfile)
# were added on the same day; no archived patch touches any of them (results.md, "Fixes after the collection").
FORBIDDEN = re.compile(r"(^|/)(\.github|\.circleci|\.gitlab|\.buildkite|\.woodpecker|vendor)(/|$)|"
                       r"(^|/)(\.gitlab-ci\.yml|\.travis\.yml|\.drone\.yml|azure-pipelines\.ya?ml|appveyor\.ya?ml|Jenkinsfile|Makefile|go\.mod|go\.sum|go\.work(\.sum)?|"
                       r"requirements[^/]*\.txt|poetry\.lock|uv\.lock|Pipfile(\.lock)?|pdm\.lock|pyproject\.toml|setup\.cfg|setup\.py|tox\.ini|noxfile\.py|"
                       r"\.?pytest\.(ini|toml)|\.coveragerc|\.golangci\.ya?ml|\.pre-commit-config\.yaml|\.flake8|ruff\.toml|\.ruff\.toml|mypy\.ini|sitecustomize\.py|usercustomize\.py)$")
CASE = REPO = WD = None; M = {}

def _decode(b): return b.decode("utf-8", "surrogateescape")

def checker_git(args, repo):
    """No inherited Git overrides, global/system config, hooks, fsmonitor, or optional index refresh writes.
    core.excludesFile is pinned: without it Git still reads $HOME/.config/git/ignore (HOME is writable in the pods),
    where a test could hide new files from the listing. safe.directory is set here because the system config that
    carried it in the image is disabled above: in the pods the working copy is a root-owned emptyDir and this process
    is uid 1000, so without it Git refuses the checkout and every integrity sample is an infrastructure error (found
    on the cluster, 2026-11-12). The repository's own config and hooks stay neutralised by the options around it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                           "-c", "core.untrackedCache=false", "-c", "core.excludesFile=/dev/null",
                           "-c", "safe.directory=*", *args],
                          cwd=repo, env=env, capture_output=True)

def numstat_paths(patch_file, cwd):
    """Every path the patch names, both sides of a rename or copy, as Git parses it (`git apply --numstat -z`, which reads
    the patch and applies nothing). Raises ValueError on any error or on output it cannot parse."""
    p = subprocess.run(["git", "apply", "--numstat", "-z", patch_file], cwd=cwd, capture_output=True)
    if p.returncode: raise ValueError("git apply --numstat failed: " + _decode(p.stderr)[-200:])
    fields, paths, i = p.stdout.split(b"\0"), set(), 0
    if fields and fields[-1] == b"": fields.pop()                       # the output ends with a NUL
    while i < len(fields):
        cols = fields[i].split(b"\t", 2)                        # a path may itself contain a tab
        if len(cols) != 3: raise ValueError(f"unexpected numstat record {fields[i][:80]!r}")
        if cols[2]: paths.add(_decode(cols[2])); i += 1
        else:                                                           # rename/copy: "a\td\t" NUL src NUL dst NUL
            if i + 2 >= len(fields) or not fields[i + 1] or not fields[i + 2]: raise ValueError("truncated rename record")
            paths |= {_decode(fields[i + 1]), _decode(fields[i + 2])}; i += 3
    if not paths: raise ValueError("the patch names no path")
    return paths

def status_entries(cwd):
    """{path: two-letter status} of the working copy, untracked files included, from `git status --porcelain -z`."""
    p = checker_git(["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"], cwd)
    if p.returncode: raise ValueError("git status failed: " + _decode(p.stderr)[-200:])
    out = {}
    for rec in p.stdout.split(b"\0"):
        if not rec: continue
        if len(rec) < 4 or rec[2:3] != b" ": raise ValueError(f"unexpected status record {rec[:80]!r}")
        out[_decode(rec[3:])] = rec[:2]
    return out

def changed_by(before, after):
    return {f for f in set(before) | set(after) if before.get(f) != after.get(f)}

def bad_paths(paths):
    return sorted(f for f in paths if TESTFILE.search(f) or FORBIDDEN.search(f))

def overlay():
    """Build products of the preparation (compiled extensions...) go over the working copy, excluded from git."""
    if os.path.isdir(f"{CASE}/overlay"):
        subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/overlay/", f"{REPO}/"], check=True)
    if os.path.exists(f"{CASE}/overlay.list"):
        with open(f"{REPO}/.git/info/exclude", "a") as x: x.write(open(f"{CASE}/overlay.list").read())

def fresh():
    # the working copy is an empty dir owned by root (mode 0777): copy the content, never the dir's own owner or times
    # Reproduction resets this directory repeatedly: timestamps/size alone can miss same-size edits in one second.
    subprocess.run(["rsync", "-rl", "--checksum", "--delete", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    overlay()

def sh(cmd, cwd=None, timeout=None):
    t, cwd = time.monotonic(), cwd or REPO
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, p.stdout, time.monotonic() - t
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), time.monotonic() - t

def runs(cmd, n, prepare=None):
    out = []
    for i in range(n):
        if prepare is not None: prepare()
        rc, o, dt = sh(cmd, cwd=WD, timeout=RUN_TIMEOUT)
        tail = o.strip().splitlines()[-1][:200] if o.strip() else ""
        out.append({"rc": rc, "s": round(dt, 1), "tail": tail})
        if i == 0: open(f"/tmp/run-output.txt", "w").write(o[-60000:])
    return out

GIT_METADATA = (".git", ".git/config", ".git/info/exclude", ".git/index", ".git/HEAD")

def fingerprint(path):
    try: info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError): return ("missing",)
    if stat.S_ISLNK(info.st_mode): return ("link", os.readlink(path))
    if stat.S_ISREG(info.st_mode):
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""): digest.update(chunk)
        return ("file", digest.hexdigest(), info.st_mode & 0o777)
    return ("other", info.st_mode)

def ignore_files(repo):
    """Every .gitignore under the checkout, found on disk (never through Git, which honours them). A test that creates
    new/.gitignore containing "*" hides everything in new/ from `git ls-files --others --exclude-standard`, itself
    included; listing the files here makes the new .gitignore count as a change. Symlinked directories are not followed."""
    found = set()
    for directory, dirs, files in os.walk(repo):
        if directory == repo and ".git" in dirs: dirs.remove(".git")
        if ".gitignore" in files or ".gitignore" in dirs:
            found.add(os.path.relpath(os.path.join(directory, ".gitignore"), repo))
    return found

def tree_state(repo, baseline=None):
    """Retain every pre-test path and hash checker metadata. Never consult changed Git metadata after a test.
    New non-ignored files are added only when the metadata is intact; the earlier file list is never replaced.
    Every .gitignore on disk is fingerprinted in both states, so a new or edited ignore file is itself a change.
    This detects persistent changes, not in-process tampering or change-and-restore races.
    """
    metadata = {name: fingerprint(os.path.join(repo, name)) for name in GIT_METADATA}
    names = set(baseline[1]) if baseline is not None else set()
    names.update(ignore_files(repo))
    if baseline is not None and any(metadata[name] != baseline[1][name] for name in GIT_METADATA):
        status = baseline[0]  # comparing metadata/content is sufficient; do not run Git on altered config/index
    else:
        status = status_entries(repo)
        p = checker_git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo)
        if p.returncode: raise ValueError("cannot enumerate working tree")
        names.update(_decode(raw) for raw in p.stdout.split(b"\0") if raw)
    content = {name: fingerprint(os.path.join(repo, name)) for name in names if name not in GIT_METADATA}
    content.update(metadata)
    return status, content


def checked_run(cmd, repo, cwd, output_path=None):
    try:
        # The checkout was copied, so the index holds stale stat data: the first plain `git status`, `git diff` or
        # `git describe --dirty` run by the suite would rewrite .git/index and look like tampering. Refresh it once,
        # before the baseline; the exit code is ignored (modified files make it non-zero), a broken index fails below.
        checker_git(["update-index", "-q", "--refresh"], repo)
        before = tree_state(repo)
        rc, output, dt = sh(cmd, cwd=cwd, timeout=RUN_TIMEOUT)
        if output_path:
            with open(output_path, "w") as f: f.write(output[-60000:])
        after = tree_state(repo, baseline=before)
    except (ValueError, OSError) as e:
        return {"outcome": "infra_error", "why": f"cannot verify test-tree integrity: {e}"}
    sample = {"rc": rc, "s": round(dt, 1), "tail": output.strip().splitlines()[-1][:200] if output.strip() else ""}
    if before != after:
        paths = sorted(changed_by(before[0], after[0]) | changed_by(before[1], after[1]))
        return {"outcome": "test_changed_tree", "why": "test command changed the working tree: " + ", ".join(paths[:6]), "run": sample}
    return {"outcome": "sampled", "run": sample}


def fixed_runs(cmd, n):
    """Calibrate the validation integrity rule on the maintainer fix, starting clean for every sample/phase.
    Preserve command exit codes separately from integrity outcomes: side effects are a case limitation, not a bad fix.
    """
    samples = []
    for i in range(n):
        fresh()
        rc, output, _ = sh("git apply --binary /in/fix.diff")
        if rc: raise ValueError("maintainer fix does not apply: " + output[-200:])
        check = checked_run(cmd, REPO, WD, output_path="/tmp/run-output.txt" if i == 0 else None)
        sample = check.pop("run", {"rc": None})
        samples.append({**sample, "integrity": check})
    return samples


def main():
    global CASE, M, REPO, WD
    CASE = f"/srv/ci/cases/{os.environ['CASE_ID']}"
    M = json.load(open(f"{CASE}/meta.json"))          # public broken-tree metadata only
    M["hidden_cmd"] = os.environ.get("HIDDEN_COMMAND", "")
    REPO = f"{CASE}/repo"; WD = os.path.normpath(os.path.join(REPO, M.get("workdir", ".")))
    mode = sys.argv[1]; r = {"id": M["id"], "mode": mode}
    if mode not in ("validate-run", "repro"): fresh()
    if mode == "repro":
        which, n = sys.argv[2], int(sys.argv[3]); r["tree"] = which
        # repro no longer starts with fresh(): each tree restores its own checkout. A mistyped tree would otherwise run
        # the command in the empty working directory and come back as an ordinary "does not reproduce".
        if which not in ("broken", "fixed", "hidden-broken", "fixed-agent-cache"):
            raise SystemExit(f"unknown repro tree {which!r}: broken | fixed | hidden-broken | fixed-agent-cache")
        if which == "hidden-broken":
            if not M.get("hidden_cmd"):
                r.update(not_applicable=True); print("EXECUTOR " + json.dumps(r)); return
        # "fixed-agent-cache": the maintainer's fix in the environment agent patches are validated in (the broken-tree
        # dependency cache; pod.py mounts the fixed-tree cache only for "fixed"). Only Go has two caches.
        if which == "fixed-agent-cache" and M.get("language") != "Go":
            r.update(not_applicable=True); print("EXECUTOR " + json.dumps(r)); return
        fixed_tree = which in ("fixed", "fixed-agent-cache")
        if which == "broken": r["prep_compiles"] = M.get("broken_compiles")   # recorded by preparation (Go); None otherwise
        def restore_broken():
            fresh()
            if which == "hidden-broken":
                rc, o, _ = sh("git apply --binary /in/hidden.diff")
                if rc: raise ValueError("hidden tests do not apply: " + o[-200:])
        try:
            r["runs"] = fixed_runs(M["test_cmd"], n) if fixed_tree else runs(M["hidden_cmd"] if which == "hidden-broken" else M["test_cmd"], n, prepare=restore_broken)
            if fixed_tree and M.get("hidden_cmd"):
                r["hidden_runs"] = fixed_runs(M["hidden_cmd"], n)
        except ValueError as e:
            r.update(error=str(e)); print("EXECUTOR " + json.dumps(r)); return
        r["pass"] = sum(x["rc"] == 0 for x in r["runs"]); r["fail"] = n - r["pass"]
        try: r["output_head"] = open("/tmp/run-output.txt").read()[-6000:]
        except OSError: pass
    elif mode == "run":
        # Audit mode (12/11, after the collection): apply an optional patch, optionally the maintainer's test changes, run one
        # command and print its whole output. Classifies nothing; used to read hidden-test failures and to run probes.
        # Since 2026-11-12 (after the audit): if anything fails to apply, the command is NOT run (it would run on the wrong
        # tree); the log ends with OUTPUT_END rc=apply_failed. Every recorded audit log shows rc=0 on each apply.
        with_hidden, cmd = sys.argv[2] == "1", sys.argv[3]
        cmd = {"TEST": M["test_cmd"], "HIDDEN": M.get("hidden_cmd", "")}.get(cmd, cmd)
        steps = []
        if os.path.exists("/in/patch.diff") and open("/in/patch.diff").read().strip():
            steps.append(("patch", "git apply --binary --whitespace=nowarn /in/patch.diff"))
        if with_hidden: steps.append(("maintainer test changes", "git apply --binary /in/hidden.diff"))
        notes, failed = apply_steps(steps, REPO)
        print("NOTES " + " | ".join(notes)); print("COMMAND " + cmd)
        if failed:
            print("ABORTED: a patch did not apply; the command was not run", flush=True); print("OUTPUT_END rc=apply_failed s=0.0", flush=True); sys.exit(1)
        rc, o, dt = sh(cmd, cwd=WD, timeout=1500)
        print("OUTPUT_BEGIN"); print(o[-120000:]); print(f"OUTPUT_END rc={rc} s={dt:.1f}", flush=True)
        sys.exit(0)
    elif mode in ("validate", "validate-prepare"):
        # Exactly ONE command per pod. The trusted host orchestrates three fresh pods for each phase.
        phase = sys.argv[2]
        if phase not in ("suite", "hidden"): raise ValueError("validate requires suite or hidden")
        r["phase"] = phase
        diff = open("/in/patch.diff").read()
        if not diff.strip(): r.update(outcome="no_patch", files=[])
        else:
            r.update(validate_patch("/in/patch.diff", REPO))
            if r.get("outcome") == "applied":
                if phase == "hidden":
                    rc, o, _ = sh("git apply --binary /in/hidden.diff")
                    if rc: r.update(outcome="hidden_tests_did_not_apply", why=o[-300:])
                if r.get("outcome") == "applied" and mode == "validate":
                    cmd = M["test_cmd"] if phase == "suite" else M.get("hidden_cmd")
                    if not cmd: r.update(outcome="infra_error", why="missing test command")
                    else: r.update(checked_run(cmd, REPO, WD))
        if mode == "validate-prepare":
            # /validation is read-only in the test container. Preparation failures still produce a normal record.
            with open("/validation/prepared.json", "w") as f: json.dump(r, f)
    elif mode == "validate-run":
        r = json.load(open("/validation/prepared.json"))
        r["mode"] = "validate"
        phase = sys.argv[2]
        if phase not in ("suite", "hidden") or r.get("phase") != phase: raise ValueError("invalid preparation record")
        if r.get("outcome") == "applied":
            cmd = M["test_cmd"] if phase == "suite" else M.get("hidden_cmd")
            if not cmd: r.update(outcome="infra_error", why="missing test command")
            else: r.update(checked_run(cmd, REPO, WD))
    print("EXECUTOR " + json.dumps(r), flush=True)

def apply_steps(steps, repo):
    """Audit mode: applies each (label, command) in order and stops at the first that fails. Returns (notes, failed)."""
    notes = []
    for label, cmd in steps:
        rc, o, _ = sh(cmd, cwd=repo); notes.append(f"{label} applied rc={rc} {o[-200:]}")
        if rc: return notes, True
    return notes, False

def validate_patch(patch_file, repo):
    """Checks (a) and (b) on a clean working copy: reads the patch's paths with Git, applies it, and reads what changed.
    Returns {"outcome": "applied", "files": [...]} when the patch is in the tree and touches nothing forbidden; otherwise
    outcome rejected_by_validator (forbidden path, or paths that could not be read) or did_not_apply."""
    try:
        declared = numstat_paths(patch_file, repo); before = status_entries(repo)
    except (ValueError, OSError) as e:
        return {"outcome": "rejected_by_validator", "why": f"could not read the patch's paths: {e}", "files": []}
    p = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", patch_file], cwd=repo, capture_output=True)
    if p.returncode: return {"outcome": "did_not_apply", "why": _decode(p.stdout + p.stderr)[-300:], "files": sorted(declared)}
    try: files = sorted(declared | changed_by(before, status_entries(repo)))
    except (ValueError, OSError) as e:
        return {"outcome": "rejected_by_validator", "why": f"could not read the changed paths: {e}", "files": sorted(declared)}
    bad = bad_paths(files)
    if bad: return {"outcome": "rejected_by_validator", "why": "touches " + ", ".join(bad[:6]), "files": files}
    return {"outcome": "applied", "files": files}

if __name__ == "__main__":
    main()
