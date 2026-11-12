#!/usr/bin/env python3
"""Fixed checks of the harness itself. No model call, no test run.
In the lab it runs INSIDE a pod made from the agent's image and pod spec with the command replaced by this file
(diag/run-selfcheck.sh), so this process is the pod's PID 1 exactly as the agent is. Fixed commands go through the
agent's own bash() and make_patch(): what a model happens to type does not decide the result. It prints
`SELFCHECK <json>` and then, like the agent, `RESULT <nonce> <json>`; before that, one command tries to write its own
RESULT line to the pod's output.
Each check has ok = true / false, or null where it does not apply (outside a pod there is no PID 1 of ours and, off
Linux, no /proc). agent/test_agent.py runs it that way on synthetic files."""
import json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent

PID1, TAG = os.getpid() == 1, f"selfcheck-{os.getpid()}"
checks = []
def check(name, ok, detail): checks.append({"check": name, "ok": ok, "detail": detail})

def alive(marker):
    """Processes, other than this one, whose command line contains the marker."""
    if os.path.isdir("/proc/self"):
        n = 0
        for p in filter(str.isdigit, os.listdir("/proc")):
            try: c = open(f"/proc/{p}/cmdline", "rb").read()
            except OSError: continue
            n += marker.encode() in c and int(p) != os.getpid()
        return n
    out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout
    return sum(marker in l for l in out.splitlines())
SLEEPER = "python3 -c 'import time; time.sleep(600)'"

def status(field):
    try: return next(l.split(":", 1)[1].strip() for l in open("/proc/self/status") if l.startswith(field + ":"))
    except (OSError, StopIteration): return None

hardened = agent.harden()
if not os.path.isdir(agent.WORK): shutil.copytree(agent.TASK, agent.WORK)
for a in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "base")): agent.git(agent.WORK, *a)

# 1. a failing command in front of a pipe is reported
a, b = agent.bash("false | cat")[0], agent.bash("true | cat")[0]
check("pipefail", a != 0 and b == 0, f"`false | cat` -> exit {a}; `true | cat` -> exit {b}")

# 2. the nonce is not in a command's environment, and PID 1's environment and output are closed to it
rc, out, _ = agent.bash("env | grep -c '^RESULT_NONCE=' || true")
check("nonce not in the command's environment", out.strip() == "0", f"RESULT_NONCE lines in `env`: {out.strip()}")
if PID1:
    rc, out, _ = agent.bash("cat /proc/1/environ > /dev/null 2>&1; echo $?")
    check("a command cannot read /proc/1/environ", out.strip() not in ("", "0"), f"cat exit {out.strip()} (process: {hardened})")
    rc, out, _ = agent.bash("""echo 'RESULT {"outcome": "finished", "patch": "", "written_by": "a tool command"}' > /proc/1/fd/1 2>/dev/null; echo $?""")
    check("a command cannot write to the pod's output", out.strip() not in ("", "0"), f"write to /proc/1/fd/1: exit {out.strip()}")
else:
    check("a command cannot read /proc/1/environ", None, "not PID 1 here: PID 1 is not this harness")
    check("a command cannot write to the pod's output", None, "not PID 1 here")

# 3. nothing a command started keeps running
rc, _, dt = agent.bash(f"{SLEEPER} {TAG}-a & {SLEEPER} {TAG}-a", limit=2); time.sleep(0.3); n = alive(f"{TAG}-a")
check("a timeout kills the command's whole process group", rc == 124 and dt < 8 and n == 0, f"exit {rc} after {dt:.1f} s (limit 2 s); processes left: {n}")
rc, out, dt = agent.bash(f"{SLEEPER} {TAG}-b & echo started"); time.sleep(0.3); n = alive(f"{TAG}-b")
check("a background child does not hold the call open and does not survive it", rc == 0 and "started" in out and dt < 5 and n == 0, f"exit {rc} after {dt:.1f} s; processes left: {n}")
rc, out, dt = agent.bash(f"python3 -c 'import os, time; os.setsid(); time.sleep(600)' {TAG}-c > /dev/null 2>&1 & sleep 0.5; echo started"); time.sleep(0.3); n = alive(f"{TAG}-c")
check("a child that left the process group (setsid) does not survive either", (n == 0) if PID1 else None,
      f"processes left: {n}" + ("" if PID1 else " (outside a pod this one survives: only PID 1 can signal every process)"))
if n and not PID1: subprocess.run(["pkill", "-f", f"{TAG}-c"])

# 4. the report does not run what the workspace's git config names; a FIFO does not block it
tmp = tempfile.mkdtemp(prefix="selfcheck-"); trap, marker = f"{tmp}/trap.sh", f"{tmp}/trap-ran"
open(trap, "w").write(f"#!/bin/sh\necho ran >> {marker}\ncat\n"); os.chmod(trap, 0o755)
open(f"{agent.WORK}/.git/config", "a").write(f'[diff]\n\texternal = {trap}\n[diff "trap"]\n\ttextconv = {trap}\n\tcommand = {trap}\n'
                                             f'[filter "trap"]\n\tclean = {trap}\n\tsmudge = {trap}\n[core]\n\tfsmonitor = {trap}\n')
open(f"{agent.WORK}/.gitattributes", "a").write("* diff=trap filter=trap\n")
open(f"{agent.WORK}/selfcheck-change.txt", "w").write("a line added by the self-check\n")
try: os.mkfifo(f"{agent.WORK}/selfcheck-fifo"); fifo = None
except OSError as e: fifo = f"mkfifo failed here ({e.strerror}): the volume does not hold FIFOs"
t = time.monotonic(); patch, left_out = agent.make_patch(); dt = time.monotonic() - t
fired = os.path.exists(marker)
check("the report runs nothing from the workspace's git config", not fired and "+a line added by the self-check" in patch,
      f"trap fired: {fired}; change in the patch: {'+a line added by the self-check' in patch}")
check("a FIFO in the workspace is left out and does not block the report", None if fifo else (len(left_out) == 1 and dt < 20), fifo or f"left out: {len(left_out)}, {dt:.1f} s")
if not fifo: os.remove(f"{agent.WORK}/selfcheck-fifo")
subprocess.run("git add -A && git diff --cached", shell=True, cwd=agent.WORK, capture_output=True, stdin=subprocess.DEVNULL)   # the old way, as a control
check("control: the same trap does fire with `git add -A && git diff --cached` in the workspace", os.path.exists(marker), f"trap fired: {os.path.exists(marker)}")
shutil.rmtree(tmp, ignore_errors=True)

# facts about where this ran (compared across runtimes by the runner)
try: open("/selfcheck-probe", "w").close(); os.remove("/selfcheck-probe"); rootfs = "writable"
except OSError as e: rootfs = f"not writable ({e.strerror})"
facts = {"pid": os.getpid(), "uid": os.getuid(), "process": hardened, "kernel": os.uname().release, "seccomp": status("Seccomp"),
         "no_new_privs": status("NoNewPrivs"), "cap_eff": status("CapEff"), "root_filesystem": rootfs,
         "service_account_token_dir": os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount")}
failed = [c["check"] for c in checks if c["ok"] is False]
print("SELFCHECK " + json.dumps({"run": agent.RUN_ID, "failed": failed, "facts": facts, "checks": checks}), flush=True)
print("RESULT " + (agent.NONCE + " " if agent.NONCE else "") + json.dumps({"run": agent.RUN_ID, "outcome": "selfcheck", "patch": "", "failed": len(failed)}), flush=True)
sys.exit(1 if failed else 0)
