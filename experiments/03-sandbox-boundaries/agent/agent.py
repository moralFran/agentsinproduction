#!/usr/bin/env python3
"""A minimal coding agent: one model loop, one tool (bash). It runs inside the sandboxed pod, has no credentials,
and reaches the model only through the gateway. It ends by printing one line, `RESULT <nonce> <json>`, with the patch,
timings and token counts; nothing is published from here.

What the tool commands can and cannot do to this harness (fourth review). They run as the same user, in the same pod:
  - every command runs with `pipefail`, so `pytest ... | tail` reports pytest's exit code, not tail's;
  - each command gets its own session; when it returns or times out, its process group is killed, and when this
    process is PID 1 of the pod (it is, in the lab) every other process of the pod is killed too, so nothing a command
    started keeps running behind the next step or behind the report;
  - the runner's nonce is taken out of the environment before the first command, and this process is made
    non-dumpable, which on Linux closes /proc/1/environ, /proc/1/fd and /proc/1/mem to the other processes of the
    same user: a command cannot read the nonce there or write a line to this process's output;
  - the patch is computed in a NEW repository made from the frozen checkout in the image plus the workspace's files.
    The workspace's own .git is never used for the report: its config is writable by the commands, and git runs what
    a config names (external diff, textconv, clean filter, fsmonitor).
None of this makes the report trustworthy. Everything in RESULT comes from a pod that ran model-chosen commands:
outcome, timings and token counts are self-reported, and the patch is just text. The patch is what the validator
judges, in another pod; the runner measures the pod's wall time itself and the gateway logs the calls it saw."""
import json, os, shutil, signal, subprocess, sys, tempfile, time

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
RUN_ID = os.environ.get("RUN_ID", "local")
MAX_CALLS = int(os.environ.get("MAX_CALLS", "40"))          # model calls
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "840"))  # cooperative; the pod's hard deadline (900 s) is set outside
TASK = os.environ.get("TASK_REPO", "/task/repo")            # the frozen checkout, read-only in the image
WORK = os.environ.get("WORK_REPO", "/work/repo")
NONCE = os.environ.pop("RESULT_NONCE", "")                  # from the runner; the tool commands never see it

SYSTEM = """You are a coding agent working in a checkout of a Python library at /work/repo.
You have one tool, bash. Commands run in /work/repo. There is no network access and you do not need any.
Task: the test file tests/test_fileutils.py fails on this commit. Find the bug in the library and fix it.
Rules: do not modify, delete or skip anything under tests/. Keep the change minimal. Run the tests to confirm.
When the tests pass, reply with a short summary of the cause and the fix, and stop."""

TOOLS = [{"name": "bash", "description": "Run a shell command in /work/repo and return its exit code and combined output (truncated).",
          "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}]

def harden():
    """Makes this process non-dumpable (Linux). -> what happened, for the report."""
    if not sys.platform.startswith("linux"): return "not linux: skipped"
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(4, 0, 0, 0, 0)                                           # PR_SET_DUMPABLE = 4
        return "non-dumpable" if libc.prctl(3, 0, 0, 0, 0) == 0 else "still dumpable"   # PR_GET_DUMPABLE = 3
    except Exception as e:
        return f"failed: {type(e).__name__}"

def sweep(pgid=None):
    """Nothing a command started keeps running: its process group, and, as PID 1 of a pod, every other process."""
    if pgid:
        try: os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
    if os.getpid() == 1 and sys.platform.startswith("linux"):               # only ever true inside the pod
        try: os.kill(-1, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass

def bash(cmd, limit=120):
    """-> (exit code, output, seconds). Output goes to files, not pipes, so a background child cannot hold the call open."""
    t = time.monotonic()
    env = {k: v for k, v in os.environ.items() if k != "RESULT_NONCE"}
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        p = subprocess.Popen(["bash", "-o", "pipefail", "-lc", cmd], cwd=WORK, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                             env=env, start_new_session=True)
        try:
            rc = p.wait(timeout=limit); timed_out = False
        except subprocess.TimeoutExpired:
            rc, timed_out = 124, True
        finally:
            sweep(p.pid); p.wait()
        fo.seek(0); fe.seek(0)
        out = (fo.read() + fe.read()).decode(errors="replace")
    if timed_out: out = f"command timed out after {limit:.0f} s"
    if len(out) > 8000: out = out[:4000] + "\n[... truncated ...]\n" + out[-4000:]
    return rc, out, time.monotonic() - t

GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/nonexistent", "LC_ALL": "C",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_ATTR_NOSYSTEM": "1",
           "GIT_TERMINAL_PROMPT": "0"}
GIT = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-c", "user.name=task", "-c", "user.email=task@example.invalid"]

def git(cwd, *args):
    return subprocess.run(GIT + list(args), cwd=cwd, env=GIT_ENV, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")

def copy_tree(src, dst, skip=()):
    """Regular files, directories and symbolic links only (links are copied as links, never followed).
    -> the special files left out (a FIFO in the workspace must not block the report)."""
    left_out = []; os.makedirs(dst, exist_ok=True)
    for e in os.scandir(src):
        if e.name in skip: continue
        d = os.path.join(dst, e.name)
        if e.is_symlink(): os.symlink(os.readlink(e.path), d)
        elif e.is_dir(follow_symlinks=False): left_out += copy_tree(e.path, d)
        elif e.is_file(follow_symlinks=False): shutil.copy2(e.path, d, follow_symlinks=False)
        else: left_out.append(e.path)
    return left_out

def make_patch():
    """The difference between the frozen checkout and the workspace's files, from a repository made here and now.
    -> (patch text, special files left out)."""
    tmp = tempfile.mkdtemp(prefix="report-")
    try:
        repo = os.path.join(tmp, "repo"); copy_tree(TASK, repo, skip=(".git",))
        for a in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "base")):
            p = git(repo, *a)
            if p.returncode != 0: raise RuntimeError(f"git {a[0]}: {p.stderr.strip()[:200]}")
        for e in os.scandir(repo):                                          # the working files become the workspace's
            if e.name == ".git": continue
            shutil.rmtree(e.path) if e.is_dir(follow_symlinks=False) else os.remove(e.path)
        left_out = copy_tree(WORK, repo, skip=(".git",))
        git(repo, "add", "-A")
        return git(repo, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color").stdout, left_out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def main():
    import anthropic
    t_start = time.monotonic()
    hardened = harden()
    shutil.copytree(TASK, WORK)
    # a repository in the workspace, for the model's own use (git status, git diff); the report does not rely on it
    for a in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "base")): git(WORK, *a)
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key="held-by-the-gateway",
                                 default_headers={"x-run-id": RUN_ID}, max_retries=0)   # no SDK retry: a retry would reuse the old timeout
    messages = [{"role": "user", "content": "Start. Run the failing tests first: python -m pytest -q tests/test_fileutils.py"}]
    r = {"run": RUN_ID, "model": MODEL, "outcome": "max_calls", "model_calls": 0, "tool_calls": 0, "in_tok": 0, "out_tok": 0,
         "model_s": 0.0, "tool_s": 0.0, "commands": [], "final_text": "",
         "harness": {"version": 4, "pipefail": True, "process": hardened, "pid1": os.getpid() == 1}}
    try:
        while r["model_calls"] < MAX_CALLS:
            left = MAX_SECONDS - (time.monotonic() - t_start)      # every call and command is bounded by the time left;
            if left <= 5: r["outcome"] = "timeout"; break            # the pod also has a hard deadline set from outside
            t = time.monotonic()
            resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages, timeout=min(300, left))
            r["model_s"] += time.monotonic() - t; r["model_calls"] += 1
            r["in_tok"] += resp.usage.input_tokens; r["out_tok"] += resp.usage.output_tokens
            messages.append({"role": "assistant", "content": resp.content})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                r["final_text"] = " ".join(b.text for b in resp.content if b.type == "text")[:1500]
                r["outcome"] = "finished" if resp.stop_reason == "end_turn" else f"stopped_{resp.stop_reason}"
                break
            results = []
            for u in uses:
                rc, out, dt = bash(str(u.input.get("command", "")), limit=max(1, min(120, MAX_SECONDS - (time.monotonic() - t_start))))
                r["tool_calls"] += 1; r["tool_s"] += dt
                r["commands"].append({"cmd": str(u.input.get("command", ""))[:300], "rc": rc, "s": round(dt, 2)})
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": f"exit code {rc}\n{out}"})
            messages.append({"role": "user", "content": results})
    except Exception as e:
        r["outcome"] = "error"; r["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    sweep()
    try:
        r["patch"], left_out = make_patch()
        if left_out: r["special_files_left_out"] = len(left_out)
    except Exception as e:
        r["patch"] = ""; r["patch_error"] = f"{type(e).__name__}: {str(e)[:300]}"
    r["total_s"] = round(time.monotonic() - t_start, 2); r["model_s"] = round(r["model_s"], 2); r["tool_s"] = round(r["tool_s"], 2)
    print("RESULT " + (NONCE + " " if NONCE else "") + json.dumps(r), flush=True)

if __name__ == "__main__":
    main()
