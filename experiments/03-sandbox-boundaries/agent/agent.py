#!/usr/bin/env python3
"""A minimal coding agent: one model loop, one tool (bash). It runs inside the sandboxed pod, has no credentials,
and reaches the model only through the gateway. It ends by printing one JSON line (RESULT ...) with the patch,
timings and token counts; nothing is published from here."""
import json, os, shutil, subprocess, time
import anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
RUN_ID = os.environ.get("RUN_ID", "local")
MAX_CALLS = int(os.environ.get("MAX_CALLS", "40"))          # model calls
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "840"))  # cooperative; the pod's hard deadline (900 s) is set outside
WORK = "/work/repo"

SYSTEM = """You are a coding agent working in a checkout of a Python library at /work/repo.
You have one tool, bash. Commands run in /work/repo. There is no network access and you do not need any.
Task: the test file tests/test_fileutils.py fails on this commit. Find the bug in the library and fix it.
Rules: do not modify, delete or skip anything under tests/. Keep the change minimal. Run the tests to confirm.
When the tests pass, reply with a short summary of the cause and the fix, and stop."""

TOOLS = [{"name": "bash", "description": "Run a shell command in /work/repo and return its exit code and combined output (truncated).",
          "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}]

def bash(cmd, limit=120):
    t = time.monotonic()
    try:
        p = subprocess.run(["bash", "-lc", cmd], cwd=WORK, capture_output=True, text=True, timeout=limit)
        out, rc = (p.stdout + p.stderr), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"command timed out after {limit:.0f} s", 124
    if len(out) > 8000: out = out[:4000] + "\n[... truncated ...]\n" + out[-4000:]
    return rc, out, time.monotonic() - t

def main():
    t_start = time.monotonic()
    shutil.copytree("/task/repo", WORK)
    g = dict(cwd=WORK, capture_output=True, text=True)
    subprocess.run("git init -q && git add -A && git -c user.name=task -c user.email=task@example.invalid commit -q -m base", shell=True, **g)
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key="held-by-the-gateway",
                                 default_headers={"x-run-id": RUN_ID}, max_retries=0)   # no SDK retry: a retry would reuse the old timeout
    messages = [{"role": "user", "content": "Start. Run the failing tests first: python -m pytest -q tests/test_fileutils.py"}]
    r = {"run": RUN_ID, "model": MODEL, "outcome": "max_calls", "model_calls": 0, "tool_calls": 0, "in_tok": 0, "out_tok": 0,
         "model_s": 0.0, "tool_s": 0.0, "commands": [], "final_text": ""}
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
    subprocess.run("git add -A", shell=True, **g)
    r["patch"] = subprocess.run("git diff --cached", shell=True, **g).stdout
    r["total_s"] = round(time.monotonic() - t_start, 2); r["model_s"] = round(r["model_s"], 2); r["tool_s"] = round(r["tool_s"], 2)
    print("RESULT " + json.dumps(r), flush=True)

if __name__ == "__main__":
    main()
