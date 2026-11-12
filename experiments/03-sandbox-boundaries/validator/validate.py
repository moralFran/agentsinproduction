#!/usr/bin/env python3
"""Validator: runs in a fresh pod with no credentials and no network. Applies a patch to a pristine checkout and
decides whether it is a fix. A patch is valid only if ALL of these hold:
  1. it is not empty and applies cleanly;
  2. it changes only files under ALLOWED (for this task: the library's own package); anything else, including a new
     conftest.py, pytest.ini or a build/config file, rejects the patch outright. What changed is read from the tree
     after the patch is applied, not only from the patch's headers;
  3. it leaves only regular files and directories, with the pristine permissions: no symbolic link, no special file,
     no mode change (v4);
  4. with everything outside ALLOWED put back from the pristine checkout, and no stray conftest/pytest config left,
     every test that passes with the maintainer's fix also runs and passes with the patch (same test ids, by junit
     report), with no failures or errors, AND pytest itself exits with code 0. Skipping tests cannot pass: a skipped
     test is not a passed test. A report that says "all passed" from a process that did not end cleanly cannot pass;
  5. the library behaves correctly when called from OUTSIDE pytest (v4, behaviour_check below).
The reference run (the maintainer's fix, in this same pod) must itself end cleanly with a report, the external check
must accept the maintainer's fix and reject the untouched checkout, and the maintainer's fix must be gone from the pod
before any patch code runs; if one of these fails, the evaluation stops: nothing is judged.

Why 5 exists. The tests run the patched library inside the pytest process that writes the report and sets the exit
code, so a patch can rewrite both from inside (controls/report-rewrite.diff). The external check does not go through
pytest: this process, which never imports the library, writes files in a new folder, starts a separate Python process
that imports the library and calls the function once, waits for it to end, kills whatever it left running, and then
looks at the folder itself. The child's output and exit code decide nothing on their own; names, contents and file
types in the folder do, compared with what this process computed beforehand from the function's documented behaviour.
The names and contents are random per run. It runs after pytest, on a second copy of the patched tree made only once
every process of the pytest run is dead. This process is non-dumpable, so the others cannot attach to it or write its
memory through /proc.

Why the reference is removed (v4). The maintainer's fix has to be in the pod to compute the reference, and patch code
runs as the same user: a patch could load it, through a symbolic link or simply by reading the file
(controls/symlink-to-reference.diff, controls/read-reference.diff). So the reference is used first and deleted, and
the validator checks it is gone, before the patched tree is imported by anything.

`flags` lists added lines that mention pytest, sys.modules, builtins, atexit, _exit, /task/ or /proc/. It is a hint
for a reader and changes no verdict: a text search is trivial to get around.
Still true: the validator cannot tell a real fix from library code written to satisfy these particular tests and
scenarios; that takes a reader.

The verdict is one line on this process's output. The child processes get no handle on that output (their own goes
to a pipe or nowhere), and with this process non-dumpable they cannot open it through /proc either; the line also
carries a nonce from the runner, taken out of the environment before any child starts.

Modes: `baseline` (no patch: must be invalid), `maintainer` (the maintainer's fix: must be valid), `patch <file>`.
Each pytest run and each external call has its own timeout."""
import json, os, re, secrets, shutil, signal, stat, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

VERSION = 4
NONCE = os.environ.pop("VALIDATION_NONCE", "")         # from the runner (validate.sh); no child process gets it
ALLOWED = ("boltons/",)
PYTEST_TIMEOUT_S, CALL_TIMEOUT_S = 300, 20
PRISTINE, FIXED = os.environ.get("TASK_REPO", "/task/repo"), os.environ.get("TASK_FIXED", "/task/fixed")
FIXED_FILE = "boltons/fileutils.py"
TARGET = ("boltons.fileutils", "rotate_file")          # what the external check calls
STRAY = ("conftest.py", "pytest.ini", "sitecustomize.py", "usercustomize.py")
FLAG_WORDS = re.compile(r"pytest|sys\.modules|builtins|atexit|_exit|/task/|/proc/")

# ---- processes -------------------------------------------------------------------------------------------------------
def harden():
    """Makes this process non-dumpable (Linux): other processes of the same user cannot attach to it or reach its
    memory, environment and file descriptors through /proc. -> what happened, for the report."""
    if not sys.platform.startswith("linux"): return "not linux: skipped"
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(4, 0, 0, 0, 0)                                           # PR_SET_DUMPABLE
        return "non-dumpable" if libc.prctl(3, 0, 0, 0, 0) == 0 else "still dumpable"
    except Exception as e:
        return f"failed: {type(e).__name__}"

def sweep(pgid=None):
    """Nothing a child started keeps running: its process group, and, as PID 1 of the pod, every other process."""
    if pgid:
        try: os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
    if os.getpid() == 1 and sys.platform.startswith("linux"):               # only ever true inside the pod
        try: os.kill(-1, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass

def pod_facts():
    """Where this process runs, for the record: user, PID, the kernel's seccomp mode for it, and whether / is writable."""
    def status(field):
        try: return next(l.split(":", 1)[1].strip() for l in open("/proc/self/status") if l.startswith(field + ":"))
        except (OSError, StopIteration): return None
    try: open("/validator-probe", "w").close(); os.remove("/validator-probe"); writable = True
    except OSError: writable = False
    return {"pid": os.getpid(), "uid": os.getuid(), "seccomp": status("Seccomp"), "no_new_privs": status("NoNewPrivs"), "cap_eff": status("CapEff"), "root_filesystem_writable": writable}

def run(cmd, cwd, timeout, env, capture=True):
    """-> (exit code or None on timeout, stdout). The child gets its own session and is swept afterwards."""
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    try: out, _ = p.communicate(timeout=timeout); rc = p.returncode
    except subprocess.TimeoutExpired: out, rc = "", None
    finally:
        sweep(p.pid)
        try: p.communicate(timeout=5)
        except Exception: pass
    return rc, out or ""

# ---- trees -----------------------------------------------------------------------------------------------------------
def allowed(rel): return (rel + "/").startswith(ALLOWED) or rel.startswith(ALLOWED)
def above_allowed(rel): return any(a.startswith(rel + "/") for a in ALLOWED)

def remove(path):
    if os.path.islink(path) or not os.path.isdir(path): os.remove(path)
    else: shutil.rmtree(path)

def fresh(path):
    if os.path.lexists(path): remove(path)
    shutil.copytree(PRISTINE, path, symlinks=True)

def snapshot(root):
    """rel path -> (kind, detail): ("dir", ""), ("file", (executable bits, content)), ("link", target), ("special", "")."""
    out = {}
    def walk(d, rel):
        for e in os.scandir(d):
            r = f"{rel}{e.name}"
            st = e.stat(follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode): out[r] = ("link", os.readlink(e.path))
            elif stat.S_ISDIR(st.st_mode): out[r] = ("dir", ""); walk(e.path, r + "/")
            elif stat.S_ISREG(st.st_mode): out[r] = ("file", (st.st_mode & 0o111, open(e.path, "rb").read()))
            else: out[r] = ("special", "")
    walk(root, "")
    return out

def tree_changes(pristine, tree):
    """What differs between the pristine checkout and a tree, read from the two trees themselves.
    -> (changed paths, problems). A problem is anything that is not a regular file or directory with the pristine
    permissions: a symbolic link, a special file, a file that became a directory or the reverse, a changed mode."""
    a, b = snapshot(pristine), snapshot(tree)
    changed = sorted(r for r in set(a) | set(b) if a.get(r) != b.get(r) and not (a.get(r, ("dir",))[0] == "dir" and b.get(r, ("dir",))[0] == "dir"))
    problems = []
    for r in changed:
        was, now = a.get(r), b.get(r)
        if now is None: continue                                            # deleted
        if now[0] == "link": problems.append(f"{r} is a symbolic link to {now[1][:80]}")
        elif now[0] == "special": problems.append(f"{r} is not a regular file")
        elif was is not None and was[0] != now[0]: problems.append(f"{r} changed from {was[0]} to {now[0]}")
        elif now[0] == "file" and now[1][0] != (was[1][0] if was else 0): problems.append(f"{r} has a changed file mode")
    return changed, problems

def restore_outside_allowed(tree):
    """Everything outside ALLOWED comes back from the pristine checkout (changed, deleted or added, whatever its
    type; nothing is written through a link). Inside ALLOWED: links and special files are replaced by the pristine
    file or removed, permissions are set back, and stray pytest/site configuration is removed."""
    def level(rel):
        here, there = os.path.join(tree, rel), os.path.join(PRISTINE, rel)
        names = set(os.listdir(here)) | (set(os.listdir(there)) if os.path.isdir(there) else set())
        for n in sorted(names):
            r = f"{rel}{n}"; t, p = os.path.join(tree, r), os.path.join(PRISTINE, r)
            if allowed(r): continue
            if above_allowed(r) and os.path.isdir(t) and not os.path.islink(t): level(r + "/"); continue
            if os.path.lexists(t): remove(t)
            if os.path.isdir(p): shutil.copytree(p, t, symlinks=True)
            elif os.path.lexists(p): shutil.copy2(p, t, follow_symlinks=False)
    level("")
    pristine = snapshot(PRISTINE)
    for r, (kind, detail) in sorted(snapshot(tree).items(), reverse=True):
        if not allowed(r) or not os.path.lexists(os.path.join(tree, r)): continue
        t, was = os.path.join(tree, r), pristine.get(r)
        if kind in ("link", "special") or (was is not None and was[0] != kind) or (kind == "file" and os.path.basename(r) in STRAY and was is None):
            remove(t)
            if was is not None and was[0] == "file": shutil.copy2(os.path.join(PRISTINE, r), t)
            elif was is not None and was[0] == "dir": shutil.copytree(os.path.join(PRISTINE, r), t, symlinks=True)
        elif kind == "file" and detail[0] != (was[1][0] if was else 0):
            os.chmod(t, (os.stat(os.path.join(PRISTINE, r)).st_mode if was else 0o644) & 0o777)

# ---- the patch as text -----------------------------------------------------------------------------------------------
def patch_files(patch):
    return sorted(set(re.findall(r"^(?:diff --git a/\S+ b/|\+\+\+ b/|--- a/|rename (?:from|to) |copy (?:from|to) )(\S+)", patch, re.M)))

def patch_problems(patch):
    """Declared in the patch itself: a file mode other than a plain file's, a binary patch."""
    out = [f"the patch declares file mode {m}" for m in sorted(set(re.findall(r"^(?:new file mode|deleted file mode|old mode|new mode) (\d+)", patch, re.M)) - {"100644"})]
    if re.search(r"^GIT binary patch", patch, re.M): out.append("the patch contains a binary change")
    return out

def flags(patch):
    return sorted({m.group(0) for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++") for m in FLAG_WORDS.finditer(l)})

# ---- pytest ----------------------------------------------------------------------------------------------------------
def run_tests(path, xml):
    """-> (outcomes by test id, summary, pytest's exit code or None). Outcome is passed / failed / error / skipped."""
    if os.path.lexists(xml): os.remove(xml)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    rc, stdout = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", f"--junitxml={xml}", "tests"],
                     path, PYTEST_TIMEOUT_S, env)
    if rc is None: return {}, f"pytest timed out after {PYTEST_TIMEOUT_S} s", None
    summary = (stdout.strip().splitlines() or [""])[-1][:200]
    out = {}
    try:
        if os.path.islink(xml): raise ValueError("report is a link")
        for tc in ET.parse(xml).getroot().iter("testcase"):
            tid = f'{tc.get("classname")}::{tc.get("name")}'
            kinds = {c.tag for c in tc}
            out[tid] = "failed" if "failure" in kinds else "error" if "error" in kinds else "skipped" if "skipped" in kinds else "passed"
    except Exception as e:
        summary += f" [no junit report: {type(e).__name__}]"; out = {}
    return out, summary, rc

# ---- the external behaviour check ------------------------------------------------------------------------------------
CHILD = ("import sys, importlib; sys.path.insert(0, sys.argv[1]); "
         "getattr(importlib.import_module(sys.argv[2]), sys.argv[3])(sys.argv[4], keep=int(sys.argv[5]))")

def rotated(files, base, keep):
    """What one rotation must leave in a folder, from the function's documented behaviour: `base` becomes generation 1,
    every generation moves up by one, the one that would pass `keep` is dropped; if `base` is missing nothing changes.
    files: name -> content. Written here, independently of the library."""
    if base not in files: return dict(files)
    root, ext = os.path.splitext(base)
    chain = [base] + [f"{root}.{i}{ext}" for i in range(1, keep + 1)]
    out = {n: c for n, c in files.items() if n not in chain}
    for src, dst in zip(chain, chain[1:]):
        if src in files: out[dst] = files[src]
    return out

def folder_matches(folder, expected):
    """None if the folder holds exactly the expected regular files with the expected contents, else what is wrong."""
    seen = {}
    for e in os.scandir(folder):
        st = e.stat(follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode): return f"{e.name} is not a regular file"
        fd = os.open(e.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f: seen[e.name] = f.read(65536).decode(errors="replace")
    if set(seen) != set(expected): return f"files are {sorted(seen)}, expected {sorted(expected)}"
    wrong = sorted(n for n in expected if seen[n] != expected[n])
    return f"wrong content in {wrong}" if wrong else None

def behaviour_check(tree, work):
    """-> (ok, {scenario: "ok" or what went wrong}). See the module docstring. `work` is a folder of this process."""
    module, func = TARGET
    tok = lambda: secrets.token_hex(4)
    def scenario(base, keep, gens, extra=True):
        root, ext = os.path.splitext(base)
        files = {f"{root}.{i}{ext}": f"generation {i} {tok()}" for i in gens}
        if extra: files[f"unrelated-{tok()}.txt"] = f"unrelated {tok()}"
        return files
    a, b, c, d, e = (f"{tok()}.log", f"{tok()}", f"{tok()}.txt", f"{tok()}.dat", f"{tok()}.log")
    plans = {  # name: (base, keep, files before the first call, contents written to `base` before each call)
        "full rotation, keep 5, with an extension": (a, 5, scenario(a, 5, range(1, 6)), [f"current {tok()}"]),
        "full rotation, keep 5, no extension":      (b, 5, scenario(b, 5, range(1, 6)), [f"current {tok()}"]),
        "keep 1, three rotations in a row":          (c, 1, {}, [f"first {tok()}", f"second {tok()}", f"third {tok()}"]),
        "only one older generation, keep 3":         (d, 3, scenario(d, 3, [1]), [f"current {tok()}"]),
        "nothing to rotate":                         (e, 2, scenario(e, 2, [1, 2]), [None]),
    }
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/nonexistent", "LANG": "C.UTF-8"}
    result = {}
    for name, (base, keep, files, writes) in plans.items():
        folder = tempfile.mkdtemp(prefix="scenario-", dir=work); cwd = tempfile.mkdtemp(prefix="cwd-", dir=work)
        for n, content in files.items(): open(os.path.join(folder, n), "w").write(content)
        state, verdict = dict(files), "ok"
        for content in writes:
            if content is not None:
                open(os.path.join(folder, base), "w").write(content); state[base] = content
            state = rotated(state, base, keep)
            rc, _ = run([sys.executable, "-I", "-B", "-c", CHILD, tree, module, func, os.path.join(folder, base), str(keep)],
                        cwd, CALL_TIMEOUT_S, env, capture=False)
            wrong = "the call did not end" if rc is None else f"the call ended with exit code {rc}" if rc != 0 else folder_matches(folder, state)
            if wrong: verdict = wrong; break
        result[name] = verdict
    return all(v == "ok" for v in result.values()), result

def remove_reference(ref):
    """The maintainer's fix leaves the pod: the reference tree and everything under FIXED. -> None, or what is left."""
    if os.path.lexists(ref): remove(ref)
    for n in os.listdir(FIXED) if os.path.isdir(FIXED) else []:
        try: remove(os.path.join(FIXED, n))
        except OSError: pass
    left = os.listdir(FIXED) if os.path.isdir(FIXED) else []
    return f"{FIXED} still holds {len(left)} entries" if left else None

# ---- one evaluation --------------------------------------------------------------------------------------------------
def emit(r):
    """One line, `VALIDATION <nonce> <json>`. The runner takes the last line that carries the nonce it made."""
    print("VALIDATION " + (NONCE + " " if NONCE else "") + json.dumps(r), flush=True); sys.exit(0)

def main(argv):
    mode = argv[1]
    r = {"mode": mode, "validator": VERSION, "process": harden(), "pod": pod_facts()}
    work = tempfile.mkdtemp(prefix="validate-"); ref, V, V2, xml = f"{work}/ref", f"{work}/v", f"{work}/v2", f"{work}/junit.xml"
    stop = lambda why: emit({**r, "valid": False, "aborted": True, "reasons": [why + ": nothing was judged"]})

    # the reference, and the two controls of the external check, before any patch code exists in this pod
    fresh(ref); shutil.copy(f"{FIXED}/{FIXED_FILE}", f"{ref}/{FIXED_FILE}")
    expected_tests, r["reference_summary"], r["reference_exit"] = run_tests(ref, xml)
    expected = {t for t, o in expected_tests.items() if o == "passed"}
    r["expected_passed"] = len(expected)
    if r["reference_exit"] != 0 or not expected: stop(f"reference run did not finish cleanly (exit {r['reference_exit']}, {len(expected)} passed)")
    ok_ref, detail_ref = behaviour_check(ref, work)
    ok_base, detail_base = behaviour_check(PRISTINE, work)
    r["external_check_controls"] = {"maintainer_fix_accepted": ok_ref, "untouched_checkout_rejected": not ok_base}
    if not ok_ref: stop("the external check rejects the maintainer's fix (" + "; ".join(f"{k}: {v}" for k, v in detail_ref.items() if v != "ok")[:200] + ")")
    if ok_base: stop("the external check accepts the untouched checkout")

    def build(path):
        """The tree to judge: pristine + (the maintainer's file | the patch). -> reasons, for a patch."""
        fresh(path); reasons = []
        if mode == "maintainer": shutil.copy(f"{ref}/{FIXED_FILE}", f"{path}/{FIXED_FILE}")
        elif mode == "patch":
            p = subprocess.run(["git", "apply", "--whitespace=nowarn", argv[2]], cwd=path, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            r["applies"] = p.returncode == 0
            if not r["applies"]: reasons.append("does not apply: " + p.stderr.strip()[-200:])
        return reasons
    reasons = []
    if mode == "patch":
        patch = open(argv[2], errors="replace").read()
        r["files"] = patch_files(patch); r["flags"] = flags(patch)
        if not patch.strip(): reasons.append("empty patch")
        reasons += patch_problems(patch)
    reasons += build(V)
    if mode == "maintainer": shutil.copytree(V, V2, symlinks=True)       # made now: the reference is about to go
    left = remove_reference(ref)
    r["reference_removed"] = left is None
    if left: stop("the maintainer's fix could not be removed before running patch code (" + left + ")")

    def checked(path):
        """Structure checks on a built tree, then everything outside ALLOWED back to pristine. -> reasons."""
        changed, problems = tree_changes(PRISTINE, path)
        r["changed"] = changed
        outside = sorted(set(f for f in changed + r.get("files", []) if not allowed(f)))
        r["touches_tests"] = any(f.startswith("tests/") for f in outside)
        out = (["changes files outside the allowed paths: " + ", ".join(outside)[:300]] if outside else []) + problems
        restore_outside_allowed(path)
        return out
    reasons += checked(V)

    got, r["summary"], r["pytest_exit"] = run_tests(V, xml)                # patch code runs here for the first time
    counts = {k: sum(1 for o in got.values() if o == k) for k in ("passed", "failed", "error", "skipped")}
    r.update(counts)
    missing = sorted(t for t in expected if got.get(t) != "passed")
    r["expected_not_passed"] = len(missing); r["expected_not_passed_sample"] = missing[:5]
    if missing: reasons.append(f"{len(missing)} of {len(expected)} expected tests did not run and pass")
    if counts["failed"] or counts["error"]: reasons.append(f"{counts['failed']} failed, {counts['error']} errors")
    if r["pytest_exit"] != 0: reasons.append(f"pytest exited with code {r['pytest_exit']}" if r["pytest_exit"] is not None else "pytest did not finish")

    # the external check, on a second copy built now that every process of the pytest run is dead
    if mode != "maintainer":
        build(V2); restore_outside_allowed(V2)
    ok, detail = behaviour_check(V2, work)
    r["external_check"] = detail
    if not ok: reasons.append("external check: " + "; ".join(f"{k}: {v}" for k, v in detail.items() if v != "ok")[:300])
    r["reasons"] = reasons; r["valid"] = not reasons
    shutil.rmtree(work, ignore_errors=True)
    emit(r)

if __name__ == "__main__":
    main(sys.argv)
