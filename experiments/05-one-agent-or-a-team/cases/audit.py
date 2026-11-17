#!/usr/bin/env python3
"""Runs ON aip-ci-01. Post-collection audit (12/11): re-runs, in executor-style Kata pods without network, (1) the
maintainer's hidden tests on every agent patch that was green but failed them, to read WHICH tests fail and why;
(2) isolation runs for QuantDinger and scc; (3) the second reviewer's probe tests for gobwas/ws on the broken tree, on the
maintainer's fix and on each distinct agent patch. Nothing here classifies or re-classifies an attempt.
usage: audit.py all | audit.py ws <label>      (label: broken, fixed, or a run id such as v2-e88f0806-r2)"""
import sys
if __name__ == "__main__":
    sys.path.pop(0)    # this folder's queue.py must not shadow the standard library's queue
import hashlib, json, os, re, subprocess
from concurrent.futures import ThreadPoolExecutor
QD, WS, SCC = "openbyteinc-quantdinger-733f7bc7", "gobwas-ws-a567dfd6", "boyter-scc-4288f7c8"
PROBE = "results/blind/codex-review-2026-11-12/writer_review_test.go"
POD_LOG_DIR = "/srv/ci/logs"

def parts(diff, keep):
    """The file sections of a diff whose path contains one of `keep` (all sections if keep is None)."""
    secs = re.split(r"(?m)^(?=diff --git )", diff)
    return "".join(x for x in secs if x.startswith("diff --git") and (keep is None or any(k in x.split("\n", 1)[0] for k in keep)))

def addfile(path, src):
    lines = open(src).read().split("\n")
    if lines[-1] == "": lines.pop()
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n" + "".join("+" + l + "\n" for l in lines)

def mk(name, text):
    f = f"/tmp/au/{name}.diff"; open(f, "w").write(text); return f

def command_rc(log):
    """A completed command's exit code, including failed tests; None for incomplete or aborted audits.
    Added after collection: apply_failed also has OUTPUT_END, but no command ran. Older logs can contain a failed
    apply followed by a command on the wrong tree; those must be retried too."""
    header, marker, _ = log.partition("\nOUTPUT_BEGIN\n")
    if not marker: return None
    notes = re.search(r"^NOTES (.*)$", header, re.M)
    if notes and any(int(rc) != 0 for rc in re.findall(r"applied rc=(-?\d+)", notes.group(1))): return None
    end = re.search(r"\nOUTPUT_END rc=(-?\d+) s=\d+(?:\.\d+)?\s*\Z", log)
    return int(end.group(1)) if end else None

def run(job):
    label, cid, patch, hidden, outdir, cmd = job
    os.makedirs(outdir, exist_ok=True)
    if sys.argv[1] != "ws" and os.path.exists(f"{outdir}/{label}.log") and "--force" not in sys.argv:
        with open(f"{outdir}/{label}.log") as f: cached = f.read()
        if command_rc(cached) is not None: return cached    # failed tests are results; failed applies are not
    pod = "au-" + re.sub(r"[^a-z0-9-]", "-", label.lower())[:50]
    a = ["python3", "cases/pod.py", "exec", cid, pod, "2400"] + (["--patch", patch] if patch else []) + ["--", "python3", "-u", "/code/executor.py", "run", "1" if hidden else "0", cmd]
    subprocess.run(a, capture_output=True, text=True)
    log_path = os.path.join(POD_LOG_DIR, f"{pod}.log")
    log = "NO LOG"
    if os.path.exists(log_path):
        with open(log_path) as f: log = f.read()
    with open(f"{outdir}/{label}.log", "w") as f: f.write(log)
    rc = command_rc(log)
    print(f"{label}: rc={rc if rc is not None else 'incomplete'}", flush=True)
    return log

def ws_job(label):
    fix = open(f"/srv/ci/secret/{WS}/fix.diff").read()
    if label == "broken": text = ""
    elif label == "fixed": text = fix
    else: text = open(f"results/patches/{label.split('-')[0]}/{label}.diff").read()
    return (label, WS, mk("ws-" + label, text + addfile("wsflate/writer_review_test.go", PROBE)), False, "results/probes/ws", "go test -count=1 -v -run TestReview ./wsflate")


def main():
    if os.path.exists("ARCHIVE") and os.environ.get("ALLOW_ARCHIVE_WRITE") != "1":
        sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")
    os.makedirs("/tmp/au", exist_ok=True)
    if sys.argv[1] == "ws":
        log = run(ws_job(sys.argv[2]))
        for l in log.split("\n"):
            if re.match(r"^(--- (PASS|FAIL)|\s+writer_review_test\.go|FAIL|ok\s|PASS$)", l): print(l[:74])
        sys.exit(0)

    jobs = []
    for v in ("v1", "v2"):                                              # 1. hidden tests on every green patch that failed them
        for l in open(f"results/attempts-{v}.jsonl"):
            r = json.loads(l)
            if r["executor"].get("outcome") == "green_fails_hidden":
                jobs.append((r["run"], r["case"], f"results/patches/{v}/{r['run']}.diff", True, "results/hidden-logs", "HIDDEN"))
    qfix = open(f"/srv/ci/secret/{QD}/fix.diff").read()                 # 2. isolation runs
    jobs += [
     ("qd-a-broken-plus-only-the-test-change-of-the-original-failing-test", QD, mk("qd-a", parts(qfix, ["tests/test_live_order_support.py"])), False, "results/probes/quantdinger", "TEST"),
     ("qd-b-broken-plus-maintainer-tests-no-source-change", QD, None, True, "results/probes/quantdinger", "HIDDEN"),
     ("qd-c-broken-plus-bitget-change-plus-maintainer-tests", QD, mk("qd-c", parts(qfix, ["live_trading/bitget.py"])), True, "results/probes/quantdinger", "HIDDEN"),
     ("qd-d-broken-untouched-fees-test-file", QD, None, False, "results/probes/quantdinger", "python -m pytest -q -p no:cacheprovider tests/test_live_exchange_fees.py"),
     ("qd-e-installed-versions", QD, None, False, "results/probes/quantdinger", "python -c \"import importlib.metadata as m; [print(n, m.version(n)) for n in ('pillow','pypdf','certifi')]\""),
     ("scc-a-broken-plus-maintainer-tests-no-source-change", SCC, None, True, "results/probes/scc", "HIDDEN"),
    ]
    shas = {}                                                           # 3. ws probes: broken, fixed, each distinct agent patch
    for v in ("v1", "v2"):
        for k in (1, 2, 3):
            run_id = f"{v}-e88f0806-r{k}"; shas.setdefault(hashlib.sha256(open(f"results/patches/{v}/{run_id}.diff", "rb").read()).hexdigest(), []).append(run_id)
    os.makedirs("results/probes/ws", exist_ok=True)
    json.dump(shas, open("results/probes/ws/distinct-patches.json", "w"), indent=1)
    jobs += [ws_job("broken"), ws_job("fixed")] + [ws_job(ids[0]) for ids in shas.values()]
    with ThreadPoolExecutor(3) as ex: list(ex.map(run, jobs))
    print("AUDIT_DONE", len(jobs), "jobs")

if __name__ == "__main__":
    main()
