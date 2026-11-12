#!/usr/bin/env python3
"""The coding agent of experiment 04 (same loop as experiment 03: one model, one bash tool). Runs inside a Kata pod in
ci-agent: no credentials, network only to the gateway's model port. It gets a fresh copy of the case snapshot (no
history after the broken commit, no remotes), the test command and the failure output from our reproduction; never the
maintainer's fix. Limits enforced from outside: the pod's activeDeadlineSeconds (25 min) and the gateway's per-run budget
(US$0.33); the tool-call limit (60) is counted here. max_tokens 4,096 per call (amendment of 12/11). Ends with one line RESULT <json> holding the patch.
Prompt caching: the newest message block is marked cache_control ephemeral (5 min) so each call re-reads the prefix
at the cache price; the gateway prices writes and reads."""
import json, os, shutil, subprocess, time
import anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
RUN_ID = os.environ["RUN_ID"]
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "60"))
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "1440"))       # cooperative; the pod's hard deadline is 1500 s
CASE = f"/srv/ci/cases/{os.environ['CASE_ID']}"; REPO = f"{CASE}/repo"
META = json.load(open(f"{CASE}/meta.json"))
WD = os.path.normpath(os.path.join(REPO, META.get("workdir", ".")))
FAILURE = open(os.environ.get("FAILURE_FILE", f"{CASE}/failure.txt")).read()[-8000:]

# The system prompt is a template per agent version (agent/prompt-v1.txt, prompt-v2.txt), chosen by PROMPT_FILE.
SYSTEM = open(os.environ.get("PROMPT_FILE", "/code/prompt-v1.txt")).read().format(language=META["language"], repo=REPO, wd=WD)
TOOLS = [{"name": "bash", "description": "Run a shell command and return its exit code and combined output (truncated).",
          "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}]

def bash(cmd, limit):
    t = time.monotonic()
    try:
        p = subprocess.run(["bash", "-lc", cmd], cwd=WD, capture_output=True, text=True, timeout=limit)
        out, rc = (p.stdout + p.stderr), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"command timed out after {limit:.0f} s", 124
    if len(out) > 10000: out = out[:5000] + "\n[... truncated ...]\n" + out[-5000:]
    return rc, out, time.monotonic() - t

def with_cache_mark(messages):
    """Copy of the history with cache_control on the last block of the last message (and on nothing else)."""
    msgs = json.loads(json.dumps(messages))
    last = msgs[-1]
    if isinstance(last["content"], str): last["content"] = [{"type": "text", "text": last["content"]}]
    blk = last["content"][-1]
    if blk.get("type") in ("text", "tool_result"): blk["cache_control"] = {"type": "ephemeral"}
    return msgs

def overlay():
    """Build products of the preparation (compiled extensions...) go over the working copy, excluded from git."""
    if os.path.isdir(f"{CASE}/overlay"):
        subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/overlay/", f"{REPO}/"], check=True)
    if os.path.exists(f"{CASE}/overlay.list"):
        with open(f"{REPO}/.git/info/exclude", "a") as x: x.write(open(f"{CASE}/overlay.list").read())

def main():
    t_start = time.monotonic()
    subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    overlay()
    g = dict(cwd=REPO, capture_output=True, text=True)
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key="held-by-the-gateway",
                                 default_headers={"x-run-id": RUN_ID}, max_retries=0)
    messages = [{"role": "user", "content": f"Test command (run from {WD}):\n{META['test_cmd']}\n\nIts output on this commit, from our CI reproduction:\n{FAILURE}"}]
    r = {"run": RUN_ID, "case": META["id"], "model": MODEL, "outcome": "max_tool_calls", "model_calls": 0, "tool_calls": 0,
         "in_tok": 0, "cache_write": 0, "cache_read": 0, "out_tok": 0, "model_s": 0.0, "tool_s": 0.0, "commands": [], "final_text": ""}
    try:
        while r["tool_calls"] < MAX_TOOL_CALLS:
            left = MAX_SECONDS - (time.monotonic() - t_start)
            if left <= 10: r["outcome"] = "timeout"; break
            t = time.monotonic()
            try:
                resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=with_cache_mark(messages), timeout=min(300, left))
            except anthropic.RateLimitError as e:            # 429 from the gateway: the run's budget is spent
                r["outcome"] = "budget_exhausted"; r["error"] = str(e)[:300]; break
            r["model_s"] += time.monotonic() - t; r["model_calls"] += 1
            u = resp.usage
            r["in_tok"] += u.input_tokens; r["out_tok"] += u.output_tokens
            r["cache_write"] += u.cache_creation_input_tokens or 0; r["cache_read"] += u.cache_read_input_tokens or 0
            messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                r["final_text"] = " ".join(b.text for b in resp.content if b.type == "text")[:2000]
                r["outcome"] = "finished" if resp.stop_reason == "end_turn" else f"stopped_{resp.stop_reason}"
                break
            results = []
            for u_ in uses:
                if r["tool_calls"] >= MAX_TOOL_CALLS:
                    results.append({"type": "tool_result", "tool_use_id": u_.id, "content": "tool-call limit reached", "is_error": True}); continue
                cmd = str(u_.input.get("command", ""))
                rc, out, dt = bash(cmd, limit=max(1, min(600, MAX_SECONDS - (time.monotonic() - t_start))))
                r["tool_calls"] += 1; r["tool_s"] += dt
                r["commands"].append({"cmd": cmd[:400], "rc": rc, "s": round(dt, 2)})
                results.append({"type": "tool_result", "tool_use_id": u_.id, "content": f"exit code {rc}\n{out}"})
            messages.append({"role": "user", "content": results})
    except Exception as e:
        r["outcome"] = "error"; r["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    subprocess.run("git add -A", shell=True, **g)
    r["patch"] = subprocess.run("git diff --cached --binary", shell=True, **g).stdout
    r["total_s"] = round(time.monotonic() - t_start, 2); r["model_s"] = round(r["model_s"], 2); r["tool_s"] = round(r["tool_s"], 2)
    print("RESULT " + json.dumps(r), flush=True)

if __name__ == "__main__":
    main()
