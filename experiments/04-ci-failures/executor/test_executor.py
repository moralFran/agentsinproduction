#!/usr/bin/env python3
"""Offline test of the executor's patch checks (a) and (b), added 2026-11-12 after the collection. Builds a SYNTHETIC
repository in a temp dir (a few made-up files, no case code, nothing from a third-party project), writes patches with
`git diff` from real edits, and runs executor.validate_patch on a fresh copy for each. Needs only git and Python.
usage: python3 executor/test_executor.py"""
import importlib.util, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("executor", os.path.join(HERE, "executor.py"))
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)          # importing runs nothing (main is guarded)

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.quotePath=true"]
def git(cwd, *a, check=True): return subprocess.run(G + list(a), cwd=cwd, capture_output=True, check=check)
def write(root, rel, text):
    path = os.path.join(root, rel); os.makedirs(os.path.dirname(path) or root, exist_ok=True); open(path, "w").write(text)

tmp = tempfile.mkdtemp(prefix="exec-test-")
BASE = os.path.join(tmp, "base")
files = {"pkg/core.py": "def f():\n    return 1\n", "tests/has space.py": "assert False\n", "tests/test_core.py": "assert True\n",
         ".github/workflows/ci.yml": "on: push\n", ".circleci/config.yml": "version: 2\n", "vendor/lib/x.go": "package x\n",
         "src/a b/mod.py": "x = 1\n", "Makefile": "all:\n", "src/notes.txt": "n\n"}
os.makedirs(BASE)
for k, v in files.items(): write(BASE, k, v)
git(BASE, "init", "-q"); git(BASE, "add", "-A"); git(BASE, "commit", "-q", "-m", "base")

def make_patch(name, edit):
    """Applies edit(work_dir) to a copy of the base repo and returns the staged diff, as agent.py produces it."""
    w = os.path.join(tmp, "mk-" + name); shutil.copytree(BASE, w); edit(w)
    git(w, "add", "-A"); d = git(w, "diff", "--cached", "--binary").stdout
    f = os.path.join(tmp, name + ".diff"); open(f, "wb").write(d); return f

def check(name, edit=None, patch_text=None):
    f = make_patch(name, edit) if edit else os.path.join(tmp, name + ".diff")
    if patch_text is not None: open(f, "wb").write(patch_text)
    w = os.path.join(tmp, "run-" + name); shutil.copytree(BASE, w)
    return ex.validate_patch(f, w)

cases = [
  # (name, edit, expected outcome, path that must be named in "why" or "files")
  ("source-only",        lambda w: write(w, "pkg/core.py", "def f():\n    return 2\n"), "applied", "pkg/core.py"),
  ("space-in-test-path", lambda w: write(w, "tests/has space.py", "assert True\n"), "rejected_by_validator", "tests/has space.py"),
  ("space-in-source",    lambda w: write(w, "src/a b/mod.py", "x = 2\n"), "applied", "src/a b/mod.py"),
  ("github-workflow",    lambda w: write(w, ".github/workflows/ci.yml", "on: [push, pull_request]\n"), "rejected_by_validator", ".github/workflows/ci.yml"),
  ("circleci-config",    lambda w: write(w, ".circleci/config.yml", "version: 2.1\n"), "rejected_by_validator", ".circleci/config.yml"),
  ("new-ci-file",        lambda w: write(w, ".gitlab/ci/test.yml", "x: 1\n"), "rejected_by_validator", ".gitlab/ci/test.yml"),
  ("vendor",             lambda w: write(w, "vendor/lib/x.go", "package x\n// y\n"), "rejected_by_validator", "vendor/lib/x.go"),
  ("makefile",           lambda w: write(w, "Makefile", "all:\n\ttrue\n"), "rejected_by_validator", "Makefile"),
  ("rename-test-away",   lambda w: os.rename(os.path.join(w, "tests/test_core.py"), os.path.join(w, "pkg/moved.py")), "rejected_by_validator", "tests/test_core.py"),
  ("delete-test",        lambda w: os.remove(os.path.join(w, "tests/has space.py")), "rejected_by_validator", "tests/has space.py"),
  ("non-ascii-test",     lambda w: write(w, "tests/tést_ünï.py", "assert True\n"), "rejected_by_validator", "tests/tést_ünï.py"),
  ("tab-in-test-name",   lambda w: write(w, "tests/a\tb.py", "assert True\n"), "rejected_by_validator", "tests/a\tb.py"),
]
fails = 0
for name, edit, want, path in cases:
    r = check(name, edit)
    seen = path in r.get("files", []) or path in r.get("why", "")
    ok = r["outcome"] == want and seen
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name:20} -> {r['outcome']:22} {r.get('why', '')[:70]!r}")

# malformed or unreadable patches are never accepted
for name, text in [("garbage", b"this is not a patch\n"), ("truncated", b"diff --git a/pkg/core.py b/pkg/core.py\n--- a/pkg/core.py\n+++ b/pkg/core.py\n@@ -1,2 +1,2 @@\n")]:
    r = check(name, patch_text=text)
    ok = r["outcome"] != "applied"; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name:20} -> {r['outcome']:22} {r.get('why', '')[:70]!r}")

# the old header regex, for the record: it does not see the path with a space
old = lambda diff: sorted({x for pair in __import__("re").findall(r"^diff --git a/(\S+) b/(\S+)", diff, __import__("re").M) for x in pair})
seen_old = old(open(os.path.join(tmp, "space-in-test-path.diff")).read())
ok = seen_old == []; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} {'old-regex-blind':20} -> old parser saw {seen_old} (the bug this test guards)")

# audit mode: a step that does not apply stops the run before the next step and before the command
w = os.path.join(tmp, "run-audit"); shutil.copytree(BASE, w)
good = make_patch("audit-good", lambda d: write(d, "pkg/core.py", "def f():\n    return 3\n"))
notes, failed = ex.apply_steps([("patch", f"git apply --binary {os.path.join(tmp, 'garbage.diff')}"), ("maintainer test changes", f"git apply --binary {good}")], w)
ok = failed and len(notes) == 1 and "rc=0" not in notes[0] and open(os.path.join(w, "pkg/core.py")).read() == files["pkg/core.py"]; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} {'audit-stops':20} -> failed={failed}, steps run {len(notes)}")
notes, failed = ex.apply_steps([("patch", f"git apply --binary {good}")], w)
ok = not failed and "rc=0" in notes[0]; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} {'audit-applies':20} -> failed={failed}")

# pattern unit checks (both directions)
for p, want in [(".github/workflows/ci.yml", True), (".circleci/config.yml", True), ("a/.github/x", True), (".github", True),
                ("docs/github.md", False), ("pkg/vendored.go", False), ("src/Makefile.py", False), ("go.mod", True), ("sub/go.sum", True),
                ("Jenkinsfile", True), ("azure-pipelines.yml", True), ("requirements-dev.txt", True), ("tests/x.py", True), ("x_test.go", True)]:
    got = bool(ex.bad_paths([p])); ok = got == want; fails += not ok
    if not ok: print(f"FAIL pattern {p!r}: forbidden/test={got}, want {want}")
n = len(cases) + 2 + 1 + 2 + 14
print(f"{n - fails}/{n} passed"); shutil.rmtree(tmp); sys.exit(1 if fails else 0)
