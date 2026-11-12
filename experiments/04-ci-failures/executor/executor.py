#!/usr/bin/env python3
"""Executor: runs in a throw-away Kata pod with NO network and NO credentials. Mounts (read-only): the case snapshot at
/in/snapshot, its offline dependencies at their prepared paths, the maintainer's fix and hidden tests at /in/secret, a
patch at /in/patch.diff. The working copy goes to an empty dir at the path the case was prepared for.
  repro <broken|fixed> <N>   run the case's test command N times on the broken tree, or on broken + maintainer's fix
  validate                   the protocol's mandatory checks on an agent patch, in order:
                               (a) it applies; (b) it touches no test, CI, lint/test configuration, dependency or lock
                               file; (c) the original test command passes 3/3; (d) with the maintainer's test-file changes
                               added on top, the hidden test command passes (when the fix had test changes).
Prints one line EXECUTOR <json>.
Harness fixes of 2026-11-12, made AFTER the v1/v2 collection and the post-collection audit (nothing recorded was re-run):
  - the changed paths come from Git itself, NUL-separated (`git apply --numstat -z` on the patch, plus `git status -z`
    before and after applying it); any error reading them rejects the patch. The old header regex missed paths with a
    space (a test file such as `tests/has space.py` passed check (b) unseen);
  - FORBIDDEN matches everything UNDER CI directories (.github/, .circleci/, ...), not only the directory name itself;
  - `run` (audit mode) stops before the command when a patch or the maintainer's test changes do not apply.
Offline test: executor/test_executor.py (synthetic repository, no case code)."""
import json, os, re, shutil, subprocess, sys, time

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
                       r"pytest\.ini|\.coveragerc|\.golangci\.ya?ml|\.pre-commit-config\.yaml|\.flake8|ruff\.toml|\.ruff\.toml|mypy\.ini|sitecustomize\.py|usercustomize\.py)$")
CASE = REPO = WD = None; M = {}

def _decode(b): return b.decode("utf-8", "surrogateescape")

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
    p = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"], cwd=cwd, capture_output=True)
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
    subprocess.run(["rsync", "-rl", "--delete", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    overlay()

def sh(cmd, cwd=None, timeout=None):
    t, cwd = time.monotonic(), cwd or REPO
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, p.stdout, time.monotonic() - t
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), time.monotonic() - t

def runs(cmd, n):
    out = []
    for i in range(n):
        rc, o, dt = sh(cmd, cwd=WD, timeout=RUN_TIMEOUT)
        tail = o.strip().splitlines()[-1][:200] if o.strip() else ""
        out.append({"rc": rc, "s": round(dt, 1), "tail": tail})
        if i == 0: open(f"/tmp/run-output.txt", "w").write(o[-60000:])
    return out

def main():
    global CASE, M, REPO, WD
    CASE = f"/srv/ci/cases/{os.environ['CASE_ID']}"
    M = json.load(open("/in/secret/meta.json"))          # the case meta plus the hidden command (never visible to the agent)
    REPO = f"{CASE}/repo"; WD = os.path.normpath(os.path.join(REPO, M.get("workdir", ".")))
    mode = sys.argv[1]; r = {"id": M["id"], "mode": mode}
    fresh()
    if mode == "repro":
        which, n = sys.argv[2], int(sys.argv[3]); r["tree"] = which
        if which == "fixed":
            rc, o, _ = sh("git apply --binary /in/secret/fix.diff")
            if rc: r.update(error="maintainer fix does not apply: " + o[-200:]); print("EXECUTOR " + json.dumps(r)); sys.exit(0)
        r["runs"] = runs(M["test_cmd"], n)
        r["pass"] = sum(x["rc"] == 0 for x in r["runs"]); r["fail"] = n - r["pass"]
        if which == "fixed" and M.get("hidden_cmd"):
            r["hidden_runs"] = runs(M["hidden_cmd"], 1)
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
        if with_hidden: steps.append(("maintainer test changes", "git apply --binary /in/secret/hidden.diff"))
        notes, failed = apply_steps(steps, REPO)
        print("NOTES " + " | ".join(notes)); print("COMMAND " + cmd)
        if failed:
            print("ABORTED: a patch did not apply; the command was not run", flush=True); print("OUTPUT_END rc=apply_failed s=0.0", flush=True); sys.exit(1)
        rc, o, dt = sh(cmd, cwd=WD, timeout=1500)
        print("OUTPUT_BEGIN"); print(o[-120000:]); print(f"OUTPUT_END rc={rc} s={dt:.1f}", flush=True)
        sys.exit(0)
    elif mode == "validate":
        diff = open("/in/patch.diff").read()
        if not diff.strip(): r.update(outcome="no_patch", files=[])
        else:
            rc, o, _ = sh("git apply --check --binary --whitespace=nowarn /in/patch.diff")
            if rc: r.update(outcome="did_not_apply", why=o[-300:], files=[])
            else: r.update(validate_patch("/in/patch.diff", REPO))
            if r.get("outcome") == "applied":
                r.pop("outcome")
                r["suite_runs"] = runs(M["test_cmd"], 3); passed = sum(x["rc"] == 0 for x in r["suite_runs"])
                r["suite_pass"] = passed
                if passed < 3: r.update(outcome="ci_still_red" if passed == 0 else "ci_flaky_after_patch")
                elif M.get("hidden_cmd"):
                    rc, o, _ = sh("git apply --binary /in/secret/hidden.diff")
                    if rc: r.update(outcome="hidden_tests_did_not_apply", why=o[-300:])
                    else:
                        r["hidden_runs"] = runs(M["hidden_cmd"], 1)
                        r["outcome"] = "green_passes_hidden" if r["hidden_runs"][0]["rc"] == 0 else "green_fails_hidden"
                else: r["outcome"] = "green_no_hidden_tests"
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
