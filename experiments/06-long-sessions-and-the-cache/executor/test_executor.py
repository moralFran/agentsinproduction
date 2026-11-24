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
         "src/a b/mod.py": "x = 1\n", "Makefile": "all:\n", "src/notes.txt": "n\n",
         # experiment 05: the shapes of the app (synthetic content)
         "lib/widgets/card.dart": "int f() => 1;\n", "test/card_test.dart": "void main() {}\n", "pubspec.yaml": "name: x\nversion: 1.0.0\n",
         "lib/internal/firebase/firestore.rules": "rules_version = '2';\n", "lib/internal/firebase/firebase.json": "{}\n",
         "lib/internal/firebase/package.json": "{}\n", "lib/internal/firebase/package-lock.json": "{}\n",
         "lib/internal/firebase/functions/index.js": "exports.a = 1;\n", "lib/internal/firebase/functions/package.json": "{}\n",
         "lib/internal/firebase/functions/tests/a.test.js": "test('a', () => {});\n",
         "lib/internal/firebase/functions/tests/e2e-functions/x.fixture": "A=1\n", "analysis_options.yaml": "linter: {}\n"}
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
  ("dart-source",        lambda w: write(w, "lib/widgets/card.dart", "int f() => 2;\n"), "applied", "lib/widgets/card.dart"),
  ("new-dart-source",    lambda w: write(w, "lib/widgets/new_card.dart", "int g() => 2;\n"), "applied", "lib/widgets/new_card.dart"),
  ("rules-source",       lambda w: write(w, "lib/internal/firebase/firestore.rules", "rules_version = '2';\n// x\n"), "applied", "lib/internal/firebase/firestore.rules"),
  ("functions-source",   lambda w: write(w, "lib/internal/firebase/functions/index.js", "exports.a = 2;\n"), "applied", "lib/internal/firebase/functions/index.js"),
  ("dart-test",          lambda w: write(w, "test/card_test.dart", "void main() { }\n"), "rejected_by_validator", "test/card_test.dart"),
  ("new-dart-test",      lambda w: write(w, "test/other_test.dart", "void main() { }\n"), "rejected_by_validator", "test/other_test.dart"),
  ("dart-test-elsewhere", lambda w: write(w, "lib/widgets/card_test.dart", "void main() { }\n"), "rejected_by_validator", "lib/widgets/card_test.dart"),
  ("jest-test",          lambda w: write(w, "lib/internal/firebase/functions/tests/a.test.js", "test('a', () => { });\n"), "rejected_by_validator", "functions/tests/a.test.js"),
  ("jest-fixture",       lambda w: write(w, "lib/internal/firebase/functions/tests/e2e-functions/x.fixture", "A=2\n"), "rejected_by_validator", "x.fixture"),
  ("jest-test-elsewhere", lambda w: write(w, "lib/internal/firebase/functions/services/b.test.js", "test('b', () => {});\n"), "rejected_by_validator", "services/b.test.js"),
  ("pubspec",            lambda w: write(w, "pubspec.yaml", "name: x\nversion: 1.0.1\n"), "rejected_by_validator", "pubspec.yaml"),
  ("package-json",       lambda w: write(w, "lib/internal/firebase/functions/package.json", "{\"a\": 1}\n"), "rejected_by_validator", "functions/package.json"),
  ("package-lock",       lambda w: write(w, "lib/internal/firebase/package-lock.json", "{\"a\": 1}\n"), "rejected_by_validator", "package-lock.json"),
  ("firebase-json",      lambda w: write(w, "lib/internal/firebase/firebase.json", "{\"a\": 1}\n"), "rejected_by_validator", "firebase.json"),
  ("firebase-e2e-json",  lambda w: write(w, "lib/internal/firebase/firebase.e2e-functions.json", "{}\n"), "rejected_by_validator", "firebase.e2e-functions.json"),
  ("analysis-options",   lambda w: write(w, "analysis_options.yaml", "linter: {rules: []}\n"), "rejected_by_validator", "analysis_options.yaml"),
  ("source-plus-test",   lambda w: (write(w, "lib/widgets/card.dart", "int f() => 3;\n"), write(w, "test/card_test.dart", "void main() {  }\n")), "rejected_by_validator", "test/card_test.dart"),
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
PATTERNS = [(".github/workflows/ci.yml", True), (".circleci/config.yml", True), ("a/.github/x", True), (".github", True),
            ("docs/github.md", False), ("src/Makefile.py", False), ("Makefile", True), ("Jenkinsfile", True), ("azure-pipelines.yml", True),
            ("tests/x.py", True), ("test/a_test.dart", True), ("test/helpers/firebase_mock.dart", True), ("integration_test/app_test.dart", True),
            ("lib/a/b_test.dart", True), ("lib/a/test_utils.dart", False), ("lib/a/latest.dart", False), ("lib/a/contest/x.dart", False),
            ("lib/internal/firebase/functions/tests/setup.js", True), ("lib/internal/firebase/functions/tests/e2e/a.test.js", True),
            ("lib/internal/firebase/functions/services/a.js", False), ("lib/internal/firebase/functions/services/a.test.js", True),
            ("lib/internal/firebase/admin-scripts/b.test.js", True), ("lib/internal/firebase/firestore.rules", False),
            ("lib/internal/firebase/storage.rules", False), ("lib/internal/firebase/firestore.indexes.json", False),
            ("pubspec.yaml", True), ("pubspec.lock", True), ("vendor/cloud_firestore/pubspec.yaml", True), ("package.json", True),
            ("lib/internal/firebase/functions/package-lock.json", True), ("lib/internal/firebase/firebase.json", True),
            ("lib/internal/firebase/firebase.e2e-functions.json", True), ("lib/internal/firebase/.firebaserc", True),
            ("analysis_options.yaml", True), ("dart_test.yaml", True), ("lib/internal/firebase/functions/jest.config.js", True),
            ("ios/Podfile.lock", True), ("ios/Podfile", False), ("lib/firebase_options.dart", False), ("lib/package_info.dart", False),
            ("web/manifest.json", False), ("lib/l10n/app_pt.arb", False), (".fvmrc", True)]
for p, want in PATTERNS:
    got = bool(ex.bad_paths([p])); ok = got == want; fails += not ok
    if not ok: print(f"FAIL pattern {p!r}: forbidden/test={got}, want {want}")
n = len(cases) + 2 + 1 + 2 + len(PATTERNS)
print(f"{n - fails}/{n} passed"); shutil.rmtree(tmp); sys.exit(1 if fails else 0)
