#!/usr/bin/env python3
"""Validator: runs in a fresh pod with no credentials and no network. Applies a patch to a pristine checkout and
decides whether it is a fix. A patch is valid only if ALL of these hold:
  1. it is not empty and applies cleanly;
  2. it changes only files under ALLOWED (for this task: the library's own package); anything else, including a new
     conftest.py, pytest.ini or a build/config file, rejects the patch outright;
  3. with everything outside ALLOWED put back from the pristine checkout, and no stray conftest/pytest config left,
     every test that passes with the maintainer's fix also runs and passes with the patch (same test ids, by junit
     report), with no failures or errors, AND pytest itself exits with code 0. Skipping tests cannot pass: a skipped
     test is not a passed test. A report that says "all passed" from a process that did not end cleanly cannot pass.
The reference run (the maintainer's fix, in this same pod) must itself end cleanly with a report; if it does not, the
evaluation stops: nothing is judged against a broken reference.
Modes: `baseline` (no patch: must be invalid), `maintainer` (the maintainer's fix: must be valid), `patch <file>`.
Each pytest run has its own timeout."""
import json, os, re, shutil, subprocess, sys
import xml.etree.ElementTree as ET

ALLOWED = ("boltons/",)
PYTEST_TIMEOUT_S = 300
PRISTINE, FIXED = "/task/repo", "/task/fixed"

def fresh(path):
    shutil.rmtree(path, ignore_errors=True); shutil.copytree(PRISTINE, path)

def restore_outside_allowed(path):
    """Everything outside ALLOWED comes from the pristine checkout; files the pristine checkout lacks are removed."""
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path)
        for f in files:
            rel = os.path.normpath(os.path.join(rel_root, f))
            if rel.startswith(ALLOWED): continue
            src = os.path.join(PRISTINE, rel)
            if os.path.isfile(src): shutil.copyfile(src, os.path.join(path, rel))
            else: os.remove(os.path.join(path, rel))
    for bad in ("conftest.py", "pytest.ini", "sitecustomize.py", "usercustomize.py"):      # inside ALLOWED too
        for root, _, files in os.walk(path):
            if bad in files and not os.path.isfile(os.path.join(PRISTINE, os.path.relpath(os.path.join(root, bad), path))):
                os.remove(os.path.join(root, bad))

def run_tests(path):
    """-> (outcomes by test id, summary, pytest's exit code or None). Outcome is passed / failed / error / skipped."""
    xml = "/tmp/junit.xml"
    if os.path.exists(xml): os.remove(xml)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", f"--junitxml={xml}", "tests"],
                           cwd=path, capture_output=True, text=True, timeout=PYTEST_TIMEOUT_S, env=env)
        summary = (p.stdout.strip().splitlines() or [""])[-1]
    except subprocess.TimeoutExpired:
        return {}, f"pytest timed out after {PYTEST_TIMEOUT_S} s", None
    out, rc = {}, p.returncode
    try:
        for tc in ET.parse(xml).getroot().iter("testcase"):
            tid = f'{tc.get("classname")}::{tc.get("name")}'
            kinds = {c.tag for c in tc}
            out[tid] = "failed" if "failure" in kinds else "error" if "error" in kinds else "skipped" if "skipped" in kinds else "passed"
    except Exception as e:
        summary += f" [no junit report: {type(e).__name__}]"; out = {}
    return out, summary, rc

mode = sys.argv[1]
r = {"mode": mode, "validator": 3}
# reference: what passes with the maintainer's fix, computed in this same pod
fresh("/tmp/ref"); shutil.copy(f"{FIXED}/boltons/fileutils.py", "/tmp/ref/boltons/fileutils.py")
ref, r["reference_summary"], r["reference_exit"] = run_tests("/tmp/ref")
expected = {t for t, o in ref.items() if o == "passed"}
r["expected_passed"] = len(expected)
if r["reference_exit"] != 0 or not expected:                 # a broken reference stops the evaluation
    r.update(valid=False, aborted=True, reasons=[f"reference run did not finish cleanly (exit {r['reference_exit']}, {len(expected)} passed): nothing was judged"])
    print("VALIDATION " + json.dumps(r), flush=True); sys.exit(0)

V = "/tmp/v"; fresh(V); reasons = []
if mode == "maintainer":
    shutil.copy(f"{FIXED}/boltons/fileutils.py", f"{V}/boltons/fileutils.py")
elif mode == "patch":
    patch = open(sys.argv[2]).read()
    files = sorted(set(re.findall(r"^(?:diff --git a/\S+ b/|\+\+\+ b/|--- a/)(\S+)", patch, re.M)))
    r["files"] = files
    outside = [f for f in files if not f.startswith(ALLOWED)]
    r["touches_tests"] = any(f.startswith("tests/") for f in files)
    if not patch.strip(): reasons.append("empty patch")
    if outside: reasons.append("changes files outside the allowed paths: " + ", ".join(outside))
    p = subprocess.run(["git", "apply", "--whitespace=nowarn", sys.argv[2]], cwd=V, capture_output=True, text=True)
    r["applies"] = p.returncode == 0
    if not r["applies"]: reasons.append("does not apply: " + p.stderr.strip()[-200:])
restore_outside_allowed(V)
got, r["summary"], r["pytest_exit"] = run_tests(V)
counts = {k: sum(1 for o in got.values() if o == k) for k in ("passed", "failed", "error", "skipped")}
r.update(counts)
missing = sorted(t for t in expected if got.get(t) != "passed")
r["expected_not_passed"] = len(missing); r["expected_not_passed_sample"] = missing[:5]
if missing: reasons.append(f"{len(missing)} of {len(expected)} expected tests did not run and pass")
if counts["failed"] or counts["error"]: reasons.append(f"{counts['failed']} failed, {counts['error']} errors")
if r["pytest_exit"] != 0: reasons.append(f"pytest exited with code {r['pytest_exit']}" if r["pytest_exit"] is not None else "pytest did not finish")
r["reasons"] = reasons; r["valid"] = not reasons
print("VALIDATION " + json.dumps(r), flush=True)
