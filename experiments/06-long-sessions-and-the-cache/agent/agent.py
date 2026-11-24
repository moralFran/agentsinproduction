#!/usr/bin/env python3
"""The agent of experiment 06 (long sessions and the prompt cache, video A-v08). One agent, one session, the harness of
experiments 04-05 (configuration A of experiment 05: it reads, plans, implements, runs the tests; when it says it is done
the harness sends the review instructions into the SAME session, then one message asking it to fix what its review
found). What V7 adds, the same in every condition unless said (protocol of 12/11, amendment of 23/11/2026):

  1. the tool `end_phase(summary)`, in every condition: the system prompt asks the agent to call it at the end of each
     phase (plan, rules, functions, app, review). In L0 it only records when the phase ended. In L2 it is also where the
     context is compacted (below). The tool list is therefore the same in both conditions.
  2. one record per model call (usage and prompt size), so the context curve and the compactions can be measured;
     the request bodies themselves are logged outside the pod, by the gateway (never published: they hold app code).
  3. a fixed one-line reminder ("run the commit's tests before you call end_phase"), appended by the harness to the
     5th request of every live attempt as a text block after the tool results, and never removed afterwards.
  4. the project guide (the snapshot's CLAUDE.md) whole, in the system prompt of every request ("monolithic guide").
     [24/11/2026, docstring only: the smoke showed the snapshot leaves CLAUDE.md out (experiment 05's exclusions), so
     the guide text every attempt got was "(the repository has no CLAUDE.md)"; criteria E7.]
  5. an attempt id at the start of the system prompt, constant within the attempt, so no attempt reads the cache
     written by another one.

Conditions (COMPACT):
  none   L0, no compaction (the model's 1M window).
  phase  L2, planned compaction: after each end_phase call the harness asks the model for a summary with a fixed prompt
         (agent/compact-prompt.txt, the last request of the old conversation, same system and tools) and replaces the
         whole history with [the original task text + that summary]. The system prompt does not change. The summary
         call counts in the attempt's cost, calls and time. The API's server-side compaction is NOT used, so that the
         mechanism is ours and fully visible.

Runs inside a pod with no credentials and one network destination, the gateway's model port. Ends with one line
RESULT <json> holding the patch (git diff of the working copy against the snapshot), the usage and the per-call log.
Prompt caching as in experiments 04-05: the newest block of each request is marked ephemeral (5 minutes)."""
import json, os, subprocess, time
import anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
COMPACT = os.environ.get("COMPACT", "none")
assert COMPACT in ("none", "phase"), COMPACT
RUN_ID = os.environ["RUN_ID"]
RUN_TOKEN = os.environ.pop("RUN_TOKEN")     # not inherited by the bash tool (see experiment 04's note: not a boundary)
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "150"))
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "2340"))       # cooperative; the pod's hard deadline is 2400 s (40 min)
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8192"))         # experiment 05 used 4,096: two attempts stopped on it
REMINDER_AT = int(os.environ.get("REMINDER_AT", "5"))
CASE = f"{os.environ.get('CASES_ROOT', '/srv/ci/cases')}/{os.environ['CASE_ID']}"; REPO = os.environ.get("REPO_DIR", f"{CASE}/repo")
META = json.load(open(f"{CASE}/meta.json"))
WD = os.path.normpath(os.path.join(REPO, META.get("workdir", ".")))
FAILURE = open(os.environ.get("FAILURE_FILE", f"{CASE}/failure.txt")).read()[-8000:]
PROMPTS = os.environ.get("PROMPT_DIR", "/code")

def prompt(name, **kw):
    return open(f"{PROMPTS}/{name}.txt").read().format(repo=REPO, wd=WD, **kw)

AREAS_HELP = META.get("areas_help") or (open(f"{PROMPTS}/areas.txt").read().strip() if os.path.exists(f"{PROMPTS}/areas.txt") else "")
REVIEW = prompt("reviewer")
COMPACT_PROMPT = prompt("compact-prompt")
REMINDER = "Reminder: run the commit's tests before you call end_phase."
BASH = {"name": "bash", "description": "Run a shell command in the repository and return its exit code and combined output (truncated).",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}
END_PHASE = {"name": "end_phase", "description": "Call this at the end of each phase of the job (plan, rules, functions, app, review), with a short summary "
             "of what the phase did and what is left. It does not change any file.",
             "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}
TOOLS = [BASH, END_PHASE]

T0 = time.monotonic()
R = {"run": RUN_ID, "case": META["id"], "config": "A", "compact": COMPACT, "model": MODEL, "outcome": "max_tool_calls", "model_calls": 0,
     "tool_calls": 0, "tool_errors": 0, "in_tok": 0, "cache_write": 0, "cache_read": 0, "out_tok": 0, "model_s": 0.0, "tool_s": 0.0,
     "roles": [], "commands": [], "calls": [], "phases": [], "compactions": [], "reminder_call": None, "reviews": 0, "final_text": ""}

class Stop(Exception):
    """A limit of the attempt was reached, or the model path failed: the attempt stops."""

def left():
    return MAX_SECONDS - (time.monotonic() - T0)

def bash(cmd, role):
    limit = max(1, min(600, left()))
    t = time.monotonic()
    try:
        # errors="replace" (23/11, after v1-t8-l2-r2 crashed on a byte cut inside a character): a byte that is not UTF-8
        # becomes U+FFFD; valid output and newline handling are exactly what text=True gave before.
        p = subprocess.run(["bash", "-o", "pipefail", "-c", cmd], cwd=WD, capture_output=True, text=True, errors="replace", timeout=limit)
        out, rc = (p.stdout + p.stderr), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"command timed out after {limit:.0f} s", 124
    if len(out) > 10000: out = out[:5000] + "\n[... truncated ...]\n" + out[-5000:]
    dt = time.monotonic() - t
    R["tool_calls"] += 1; R["tool_s"] += dt; R["tool_errors"] += rc != 0
    R["commands"].append({"role": role, "call": R["model_calls"], "cmd": cmd[:400], "rc": rc, "s": round(dt, 2)})
    return f"exit code {rc}\n{out}"

def model_call_failure(e):
    """Same classification as experiment 04: this run's own cap is an outcome (budget_exhausted); anything else on the
    model path is infrastructure (gateway_unavailable); None = not a model-path failure."""
    status = getattr(e, "status_code", None)
    if status == 429:
        return "budget_exhausted" if "run budget" in f"{e} {getattr(e, 'body', '')}" else "gateway_unavailable"
    if status == 403 or (isinstance(status, int) and status >= 500): return "gateway_unavailable"
    if isinstance(e, getattr(anthropic, "APIConnectionError", ())): return "gateway_unavailable"
    return None

def with_cache_mark(messages):
    msgs = json.loads(json.dumps(messages))
    last = msgs[-1]
    if isinstance(last["content"], str): last["content"] = [{"type": "text", "text": last["content"]}]
    blk = last["content"][-1]
    if blk.get("type") in ("text", "tool_result"): blk["cache_control"] = {"type": "ephemeral"}
    return msgs

def as_blocks(content):
    return [{"type": "text", "text": content}] if isinstance(content, str) else content

def task_text():
    cmds = META.get("test_cmds") or [META.get("test_cmd", "")]
    return (f"Task:\n{META['statement']}\n\nTests that must pass when you are done (run from {WD}):\n" + "\n".join(cmds) +
            f"\n\nTheir output on the current code:\n{FAILURE}")

class Session:
    """The one model conversation of the attempt."""
    def __init__(self, client, system):
        self.client, self.system = client, system
        self.messages = []
        self.compact_pending = False
        self.use = {"role": "single", "model_calls": 0, "tool_calls": 0, "in_tok": 0, "cache_write": 0, "cache_read": 0, "out_tok": 0, "s": 0.0}
        R["roles"].append(self.use)

    def call(self, role):
        """One model call on the current history; books usage and the per-call record. Raises Stop on a limit."""
        if left() <= 10: R["outcome"] = "timeout"; raise Stop()
        n = R["model_calls"] + 1
        if n == REMINDER_AT and R["reminder_call"] is None and self.messages and self.messages[-1]["role"] == "user":
            # 3. the reminder: a text block after the tool results of request REMINDER_AT, kept in the history afterwards
            self.messages[-1]["content"] = as_blocks(self.messages[-1]["content"]) + [{"type": "text", "text": REMINDER}]
            R["reminder_call"] = n
        t = time.monotonic()
        try:
            resp = self.client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=self.system, tools=TOOLS,
                                               messages=with_cache_mark(self.messages), timeout=min(300, left()))
        except Exception as e:
            why = model_call_failure(e)
            if why is None: raise
            R["outcome"] = why; R["error"] = f"{type(e).__name__}: {str(e)[:300]}"; raise Stop()
        dt = time.monotonic() - t
        R["model_s"] += dt; R["model_calls"] += 1; self.use["model_calls"] += 1
        u = resp.usage
        cw, cr = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
        for k, v in (("in_tok", u.input_tokens), ("out_tok", u.output_tokens), ("cache_write", cw), ("cache_read", cr)):
            R[k] += v; self.use[k] += v
        R["calls"].append({"n": n, "role": role, "in": u.input_tokens, "cw": cw, "cr": cr, "out": u.output_tokens,
                           "prompt": u.input_tokens + cw + cr, "msgs": len(self.messages), "stop": resp.stop_reason,
                           "t": round(time.monotonic() - T0, 1), "s": round(dt, 2)})
        return resp

    def compact(self):
        """L2: summary with the fixed prompt, then the history becomes [task + summary]. Same system, same tools."""
        before = R["calls"][-1]["prompt"] if R["calls"] else None
        last = self.messages[-1]
        last["content"] = as_blocks(last["content"]) + [{"type": "text", "text": COMPACT_PROMPT}]
        resp = self.call("compact")
        summary = " ".join(b.text for b in resp.content if b.type == "text").strip()
        rec = {"at_call": R["model_calls"], "prompt_before": before, "summary_chars": len(summary), "summary_stop": resp.stop_reason,
               "summary_tool_use": any(b.type == "tool_use" for b in resp.content), "t": round(time.monotonic() - T0, 1)}
        if not summary:      # the model answered with a tool call only: fall back to the agent's own end_phase summaries
            summary = "\n".join(p["summary"] for p in R["phases"]); rec["fallback"] = "end_phase summaries"
        R["compactions"].append(rec)
        self.messages = [{"role": "user", "content": task_text() + "\n\nSummary of the work so far. Your context was compacted at the end of a phase; "
                          "the working copy keeps every change you made:\n" + summary + "\n\nContinue with the next phase."}]

    def run(self, user_text):
        """Send a user message and loop until the model ends its turn. Returns its last text. Raises Stop on a limit."""
        t_in = time.monotonic()
        self.messages.append({"role": "user", "content": user_text})
        try:
            while True:
                if R["tool_calls"] >= MAX_TOOL_CALLS: R["outcome"] = "max_tool_calls"; raise Stop()
                resp = self.call("single")
                self.messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
                uses = [b for b in resp.content if b.type == "tool_use"]
                text = " ".join(b.text for b in resp.content if b.type == "text")
                if resp.stop_reason != "tool_use" or not uses:
                    if resp.stop_reason not in ("end_turn", "stop_sequence"):
                        R["outcome"] = f"stopped_{resp.stop_reason}"; raise Stop()
                    return text
                results = []
                for b in uses:
                    if R["tool_calls"] >= MAX_TOOL_CALLS:
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": "tool-call limit of the attempt reached", "is_error": True}); continue
                    self.use["tool_calls"] += 1
                    if b.name == "bash":
                        out = bash(str(b.input.get("command", "")), "single")
                    elif b.name == "end_phase":
                        R["tool_calls"] += 1
                        R["phases"].append({"n": len(R["phases"]) + 1, "call": R["model_calls"], "t": round(time.monotonic() - T0, 1),
                                            "summary": str(b.input.get("summary", ""))[:1500]})
                        out = "Phase recorded."
                        if COMPACT == "phase": self.compact_pending = True
                    else:
                        out = f"unknown tool {b.name}"
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
                self.messages.append({"role": "user", "content": results})
                if self.compact_pending:
                    self.compact_pending = False
                    self.compact()
        finally:
            self.use["s"] = round(self.use["s"] + time.monotonic() - t_in, 2)

def run_single(client, guide):
    system = (f"Attempt {RUN_ID}.\n\n" + prompt("project", areas=AREAS_HELP) + "\n\n" + prompt("single") + "\n\n" + prompt("phases") +
              "\n\nProject guide (the repository's CLAUDE.md, also in the working copy):\n" + guide)
    R["system_chars"] = len(system); R["guide_chars"] = len(guide)
    s = Session(client, system)
    R["final_text"] = s.run(task_text())[:2000]
    R["reviews"] += 1
    review = s.run(REVIEW + "\n\nYou wrote this change yourself: review it now, in this session, by these instructions. Report your findings; do not edit files in this step.")
    R["review_text"] = review[:2000]
    R["final_text"] = s.run("Fix every problem your review found, re-run the tests, and finish. If it found none, say so and finish.")[:2000]

def main():
    subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    if os.path.isdir(f"{CASE}/overlay"):       # dependencies and build products of the preparation, excluded from the diff
        subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/overlay/", f"{REPO}/"], check=True)
    if os.path.exists(f"{CASE}/overlay.list"):
        with open(f"{REPO}/.git/info/exclude", "a") as x: x.write(open(f"{CASE}/overlay.list").read())
    guide_path = f"{REPO}/CLAUDE.md"
    guide = open(guide_path).read() if os.path.exists(guide_path) else "(the repository has no CLAUDE.md)"
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key="held-by-the-gateway",
                                 default_headers={"x-run-token": RUN_TOKEN}, max_retries=0)
    try:
        run_single(client, guide)
        R["outcome"] = "finished"
    except Stop:
        pass
    except Exception as e:
        R["outcome"] = "error"; R["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    g = dict(cwd=REPO, capture_output=True, text=True)
    if R["outcome"] == "gateway_unavailable":
        R["patch"] = ""      # the attempt did not get its model calls: whatever is in the working copy is not a result
    else:
        subprocess.run("git add -A", shell=True, **g)
        R["patch"] = subprocess.run("git diff --cached --binary --no-ext-diff --no-textconv", shell=True, **g).stdout
    R["total_s"] = round(time.monotonic() - T0, 2); R["model_s"] = round(R["model_s"], 2); R["tool_s"] = round(R["tool_s"], 2)
    print("RESULT " + json.dumps(R), flush=True)

if __name__ == "__main__":
    main()
