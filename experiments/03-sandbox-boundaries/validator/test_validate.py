#!/usr/bin/env python3
"""Offline test of the validator's own functions, on a SYNTHETIC library made here (`synthlib`, a few lines, with the
same kind of bug as the task). The task's repository is never imported or run, and pytest is not needed: in the
end-to-end checks (5) the pytest run is replaced by a stand-in that says whatever each check wants it to say, which
is exactly the situation the external check is for. What this does NOT show: that pytest 9.2.0 can be rewritten the
way controls/report-rewrite.diff does it, or anything about the real task; that needs the lab (validator/revalidate.sh).
 1. Tree checks after `git apply`: a file replaced by a symbolic link, a mode change, a special file and a file
    outside the allowed path whose header the text search misses are all reported, and the restore step puts the
    pristine files back without writing through a link.
 2. flags(): added lines only.
 3. rotated(): the validator's own statement of what one rotation must leave.
 4. The external behaviour check: accepts a correct library, rejects the bug, and rejects libraries that try to look
    right (do nothing and exit 0, leave links instead of files, do it right then exit 1, hand the work to a
    background process, never return).
 5. main(), pytest replaced by a stand-in: the untouched folder is invalid, the reference is valid, a real fix is
    valid; a patch whose tests "all pass" while the bug is still there is invalid (external check); a symbolic link to
    the reference and a patch that reads the reference are invalid; the reference is gone from the pod before the
    patched tree is first run; if it cannot be removed, nothing is judged."""
import contextlib, io, json, os, shutil, stat, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
tmp = tempfile.mkdtemp(prefix="validator-test-"); P, F = f"{tmp}/pristine", f"{tmp}/fixed"
os.environ.update(TASK_REPO=P, TASK_FIXED=F)
import validate as v
v.ALLOWED, v.FIXED_FILE, v.TARGET = ("synthlib/",), "synthlib/files.py", ("synthlib.files", "rotate_file")
ok = True
def check(name, cond, detail):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), name, *(() if "--short" in sys.argv else ("-", detail)), flush=True)

HEAD = "import os\ndef rotate_file(filename, *, keep=5):\n    if not os.path.exists(filename): return\n    root, ext = os.path.splitext(filename)\n    names = [filename] + [f'{root}.{i}{ext}' for i in range(1, keep + 1)]\n"
MOVE = "    for src, dst in reversed(list(zip(names, names[1:]))):\n        if os.path.exists(src): os.rename(src, dst)\n"
DROP = "    if os.path.exists(names[-1]): os.remove(names[-1])\n"
GOOD, BUGGY = HEAD + DROP + MOVE, HEAD + MOVE + DROP          # the bug: the oldest generation is removed after the moves
def make_fixed():
    shutil.rmtree(F, ignore_errors=True); os.makedirs(f"{F}/synthlib"); open(f"{F}/synthlib/files.py", "w").write(GOOD)
os.makedirs(f"{P}/synthlib"); os.makedirs(f"{P}/tests")
open(f"{P}/synthlib/__init__.py", "w").close(); open(f"{P}/synthlib/files.py", "w").write(BUGGY)
open(f"{P}/tests/test_files.py", "w").write("# stands for the task's tests; never run here\n"); open(f"{P}/pyproject.toml", "w").write("[tool.pytest.ini_options]\n")
make_fixed()
def applied(diff, name):
    """A fresh copy of the pristine folder with the patch applied by plain `git apply`. -> (folder, patch file)."""
    t, pf = f"{tmp}/{name}", f"{tmp}/{name}.diff"; open(pf, "w").write(diff)
    shutil.copytree(P, t, symlinks=True)
    r = subprocess.run(["git", "apply", "--whitespace=nowarn", pf], cwd=t, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return t, pf
def links(t): return [os.path.join(d, n) for d, ds, fs in os.walk(t) for n in ds + fs if os.path.islink(os.path.join(d, n))]
RENAME = "diff --git a/{0} b/{1}\nsimilarity index 100%\nrename from {0}\nrename to {1}\n"
LINK = "diff --git a/{0} b/{0}\nnew file mode 120000\n--- /dev/null\n+++ b/{0}\n@@ -0,0 +1 @@\n+{1}\n\\ No newline at end of file\n"
SYMLINK = RENAME.format("synthlib/files.py", "synthlib/files_before.py") + LINK.format("synthlib/files.py", f"{F}/synthlib/files.py")

# 1. tree checks
t, pf = applied(SYMLINK, "t-symlink"); changed, problems = v.tree_changes(P, t); declared = v.patch_problems(open(pf).read())
was_link = os.path.islink(f"{t}/synthlib/files.py"); v.restore_outside_allowed(t)
check("1a a file replaced by a symbolic link to the reference is reported, then put back", was_link and any("symbolic link" in p for p in problems) and any("120000" in d for d in declared)
      and not links(t) and open(f"{t}/synthlib/files.py").read() == BUGGY,
      f"git apply made the link: {was_link}; problems: {problems}; declared: {declared}; links left after restore: {len(links(t))}")
t, pf = applied("diff --git a/synthlib/files.py b/synthlib/files.py\nold mode 100644\nnew mode 100755\n", "t-mode"); changed, problems = v.tree_changes(P, t)
v.restore_outside_allowed(t); mode = stat.S_IMODE(os.stat(f"{t}/synthlib/files.py").st_mode)
check("1b a mode change is reported and undone", any("file mode" in p for p in problems) and not mode & 0o111, f"problems: {problems}; mode after restore: {mode:o}")
t = f"{tmp}/t-fifo"; shutil.copytree(P, t); os.mkfifo(f"{t}/synthlib/pipe"); changed, problems = v.tree_changes(P, t); v.restore_outside_allowed(t)
check("1c a special file is reported and removed", any("not a regular file" in p for p in problems) and not os.path.lexists(f"{t}/synthlib/pipe"), f"problems: {problems}")
quoted = 'diff --git "a/conftest\\303\\251.py" "b/conftest\\303\\251.py"\nnew file mode 100644\n--- /dev/null\n+++ "b/conftest\\303\\251.py"\n@@ -0,0 +1 @@\n+x = 1\n'
t, pf = applied(quoted, "t-quoted"); by_text = v.patch_files(open(pf).read()); changed, problems = v.tree_changes(P, t)
outside = [c for c in changed if not v.allowed(c)]; v.restore_outside_allowed(t); left = sorted(set(os.listdir(t)) - set(os.listdir(P)))
check("1d a file outside the allowed path is found in the tree even when the header search misses it", by_text == [] and len(outside) == 1 and not left,
      f"paths found in the patch text: {by_text}; outside the allowed path in the tree: {len(outside)}; left after restore: {left}")
victim = f"{tmp}/victim.txt"; open(victim, "w").write("untouched")
t, pf = applied(RENAME.format("tests/test_files.py", "tests/old.py") + LINK.format("tests/test_files.py", victim), "t-through")
changed, problems = v.tree_changes(P, t); v.restore_outside_allowed(t)
check("1e the restore step does not write through a link", open(victim).read() == "untouched" and not links(t) and sorted(os.listdir(f"{t}/tests")) == ["test_files.py"]
      and open(f"{t}/tests/test_files.py").read() == open(f"{P}/tests/test_files.py").read(), f"file the link pointed to: {open(victim).read()!r}; tests/ after restore: {sorted(os.listdir(f'{t}/tests'))}")

# 2. flags
text = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,4 @@\n import pytest\n-import builtins\n+import sys; sys.modules['a'] = 1\n+from _pytest import reports\n+open('/task/fixed/x')\n plain\n"
check("2 flags come from added lines only", v.flags(text) == ["/task/", "pytest", "sys.modules"] and v.flags("+x = 1\n") == [], f"flags: {v.flags(text)}")

# 3. the validator's own model of one rotation
m = v.rotated({"a.log": "0", "a.1.log": "1", "a.2.log": "2", "other": "x"}, "a.log", 2)
check("3 rotated(): generations move up, the last is dropped, the rest is untouched", m == {"a.1.log": "0", "a.2.log": "1", "other": "x"}
      and v.rotated({"a.1.log": "1"}, "a.log", 2) == {"a.1.log": "1"} and v.rotated({"a": "0"}, "a", 1) == {"a.1": "0"}, f"{m}")

# 4. the external check, against libraries written here
def lib(name, body):
    d = f"{tmp}/lib-{name}"; os.makedirs(f"{d}/synthlib"); open(f"{d}/synthlib/__init__.py", "w").close(); open(f"{d}/synthlib/files.py", "w").write(body); return d
work = f"{tmp}/work"; os.mkdir(work)
def ext(name, body):
    good, detail = v.behaviour_check(lib(name, body), work); return good, [k for k, x in detail.items() if x != "ok"], detail
g, bad, _ = ext("good", GOOD)
check("4a a correct library is accepted", g and not bad, f"scenarios not ok: {bad}")
g, bad, d = ext("buggy", BUGGY)
check("4b the bug is rejected", not g and len(bad) == 3 and all("keep" in k for k in bad), f"rejected in {len(bad)} of {len(d)} scenarios: {bad}")
cheats = {
  "does nothing, prints success, exits 0": "def rotate_file(filename, *, keep=5):\n    print('rotated, all good')\n",
  "leaves links instead of files": HEAD + DROP + "    for src, dst in reversed(list(zip(names, names[1:]))):\n        if os.path.exists(src):\n            os.rename(src, src + '.stash'); os.symlink(src + '.stash', dst)\n",
  "does it right, then exits 1": GOOD + "    os._exit(1)\n",
  "hands the work to a background process": HEAD + "    import subprocess, sys\n    subprocess.Popen([sys.executable, '-c', 'import time, os, sys; time.sleep(1); os.rename(sys.argv[1], sys.argv[2])', filename, names[1]])\n",
}
res = {k: ext(f"cheat{i}", body)[0] for i, (k, body) in enumerate(cheats.items())}
check("4c libraries that only look right are rejected", not any(res.values()), "; ".join(f"{k}: {'ACCEPTED' if x else 'rejected'}" for k, x in res.items()))
v.CALL_TIMEOUT_S = 2; g, bad, d = ext("hangs", "import time\ndef rotate_file(filename, *, keep=5):\n    time.sleep(600)\n"); v.CALL_TIMEOUT_S = 20
check("4d a call that never returns is cut and rejected", not g and "did not end" in next(iter(d.values())), f"{next(iter(d.values()))}")

# 5. main(), with a stand-in for the pytest run
state = {}
def fake_pytest(honest):
    def run_tests(path, xml):
        first = "reference_seen" not in state; state["reference_seen"] = True
        if not first:                                    # the patched tree is about to run: where is the reference?
            state["reference_present_at_first_run"] = bool(os.path.isdir(F) and os.listdir(F)) or any(os.path.exists(os.path.join(os.path.dirname(path), "ref", x)) for x in ("synthlib",))
        fixed = first or not honest or open(f"{path}/synthlib/files.py").read() == GOOD     # not honest: "all passed", whatever the code
        out = {"tests.test_files::a": "passed", "tests.test_files::b": "passed" if fixed else "failed"}
        return out, ("2 passed" if fixed else "1 failed, 1 passed"), (0 if fixed else 1)
    return run_tests
def judge(mode, diff=None, honest=True):
    make_fixed(); state.clear(); v.run_tests = fake_pytest(honest); argv = ["validate.py", mode]
    if diff is not None: pf = f"{tmp}/judge-{len(os.listdir(tmp))}.diff"; open(pf, "w").write(diff); argv.append(pf)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit): v.main(argv)
    return json.loads(buf.getvalue().split("VALIDATION ", 1)[1])
FIX = "--- a/synthlib/files.py\n+++ b/synthlib/files.py\n@@ -3,6 +3,6 @@\n     if not os.path.exists(filename): return\n     root, ext = os.path.splitext(filename)\n     names = [filename] + [f'{root}.{i}{ext}' for i in range(1, keep + 1)]\n+    if os.path.exists(names[-1]): os.remove(names[-1])\n     for src, dst in reversed(list(zip(names, names[1:]))):\n         if os.path.exists(src): os.rename(src, dst)\n-    if os.path.exists(names[-1]): os.remove(names[-1])\n"
FIX = "diff --git a/synthlib/files.py b/synthlib/files.py\n" + FIX
b, mt, fx = judge("baseline"), judge("maintainer"), judge("patch", FIX)
check("5a untouched folder invalid, reference valid, a real fix valid", b["valid"] is False and mt["valid"] is True and fx["valid"] is True and fx["changed"] == ["synthlib/files.py"]
      and b["external_check_controls"] == {"maintainer_fix_accepted": True, "untouched_checkout_rejected": True},
      f"baseline {b['valid']} ({'; '.join(b['reasons'])[:90]}), maintainer {mt['valid']}, fix {fx['valid']} {fx.get('reasons')}")
NOOP = "diff --git a/synthlib/__init__.py b/synthlib/__init__.py\n--- a/synthlib/__init__.py\n+++ b/synthlib/__init__.py\n@@ -0,0 +1 @@\n+# the bug stays; imagine the report rewritten from in here\n"
rw = judge("patch", NOOP, honest=False)
check("5b tests that 'all pass' with the bug still there: invalid, by the external check alone", rw["valid"] is False and rw["failed"] == 0 and rw["pytest_exit"] == 0 and len(rw["reasons"]) == 1 and rw["reasons"][0].startswith("external check"),
      f"stand-in pytest said {rw['summary']!r}, exit {rw['pytest_exit']}; valid {rw['valid']}; reasons: {[x[:60] for x in rw['reasons']]}")
sl = judge("patch", SYMLINK); gone_sl = state.get("reference_present_at_first_run") is False
READ = ("diff --git a/synthlib/__init__.py b/synthlib/__init__.py\n--- a/synthlib/__init__.py\n+++ b/synthlib/__init__.py\n@@ -0,0 +1,6 @@\n+import importlib.util as u, sys\n+try:\n"
        f"+    s = u.spec_from_file_location('synthlib.files', '{F}/synthlib/files.py'); m = u.module_from_spec(s); sys.modules['synthlib.files'] = m; s.loader.exec_module(m)\n"
        "+except OSError:\n+    sys.modules.pop('synthlib.files', None)\n+\n")
rd = judge("patch", READ, honest=False); gone_rd = state.get("reference_present_at_first_run") is False
check("5c a link to the reference and a patch that reads the reference are invalid; the reference is gone before patch code runs",
      sl["valid"] is False and any("symbolic link" in x for x in sl["reasons"]) and rd["valid"] is False and any(x.startswith("external check") for x in rd["reasons"]) and gone_sl and gone_rd
      and sl["reference_removed"] and rd["flags"] == ["sys.modules"],
      f"link: valid {sl['valid']}, {[x[:48] for x in sl['reasons']]}; read: valid {rd['valid']} although the stand-in pytest said {rd['summary']!r}, flags {rd['flags']}; reference present when the patched tree first ran: {not gone_sl} / {not gone_rd}")
make_fixed(); state.clear(); v.run_tests = fake_pytest(True); keep = v.remove_reference
v.remove_reference = lambda ref: "simulated: the folder cannot be emptied"
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit): pf = f"{tmp}/last.diff"; open(pf, "w").write(FIX); v.main(["validate.py", "patch", pf])
ab = json.loads(buf.getvalue().split("VALIDATION ", 1)[1]); v.remove_reference = keep
check("5d the reference cannot be removed: nothing is judged", ab["valid"] is False and ab.get("aborted") and "reference_present_at_first_run" not in state, f"valid {ab['valid']}, aborted {ab.get('aborted')}: {ab['reasons'][0][:90]}; patched tree run: {'reference_present_at_first_run' in state}")
os.chmod(f"{F}/synthlib", 0o500); left = v.remove_reference(f"{tmp}/no-ref"); os.chmod(f"{F}/synthlib", 0o700)
check("5e remove_reference() says so when a file stays", left is not None, f"{left}")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
