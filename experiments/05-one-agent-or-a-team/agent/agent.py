#!/usr/bin/env python3
"""The agent of experiment 05 (one agent vs a team), in two configurations chosen by CONFIG:

  A  one agent, one session: it reads, plans, implements and runs the tests. When it says it is done, the harness sends
     the review instructions (agent/reviewer.txt) into the SAME session, then one message asking it to fix what its own
     review found.
  B  a team: an orchestrator session that plans and dispatches one subagent per area (rules, functions, flutter) through
     the `dispatch` tool, and a reviewer subagent through the `review` tool. Every subagent starts with its own context:
     the shared project notes, its role prompt and the task text the orchestrator wrote; never the orchestrator's
     conversation. The reviewer gets the same review instructions as A (agent/reviewer.txt). If the orchestrator ends
     without a review, the harness runs one and hands it the report once.

What differs between A and B is how the work and the context are split, and how the review runs (A reviews in its own
session; B's orchestrator calls a fresh reviewer subagent, and the harness runs one if it never does). [Corrected on
17/11/2026 after an external review; it said "only how the context is split". Docstring only.] Same model, same shared project notes, same bash tool,
same review instructions, same working copy, and the same limits for the whole attempt, summed over every agent of the
team: MAX_SECONDS of wall clock, MAX_TOOL_CALLS tool calls (every bash command of any agent, and every dispatch/review
call of the orchestrator), and the gateway's budget for the run (one run token for all of them).

Runs inside a pod with no credentials and one network destination, the gateway's model port. Ends with one line
RESULT <json> holding the patch (git diff of the working copy against the snapshot) and the usage per role.
Prompt caching as in experiment 04: the newest block of each request is marked ephemeral."""
import json, os, subprocess, time
import anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
CONFIG = os.environ.get("CONFIG", "A")
RUN_ID = os.environ["RUN_ID"]
RUN_TOKEN = os.environ.pop("RUN_TOKEN")     # not inherited by the bash tool (see experiment 04's note: not a boundary)
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "150"))
MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "2340"))       # cooperative; the pod's hard deadline is 2400 s (40 min)
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4096"))
CASE = f"{os.environ.get('CASES_ROOT', '/srv/ci/cases')}/{os.environ['CASE_ID']}"; REPO = os.environ.get("REPO_DIR", f"{CASE}/repo")
META = json.load(open(f"{CASE}/meta.json"))
WD = os.path.normpath(os.path.join(REPO, META.get("workdir", ".")))
FAILURE = open(os.environ.get("FAILURE_FILE", f"{CASE}/failure.txt")).read()[-8000:]
PROMPTS = os.environ.get("PROMPT_DIR", "/code")
AREAS = ["rules", "functions", "flutter"]

def prompt(name, **kw):
    return open(f"{PROMPTS}/{name}.txt").read().format(repo=REPO, wd=WD, **kw)

# The same project notes for every agent of A and B. The layout of the three areas comes from agent/areas.txt (the
# same text for every task; a task's meta.json may override it with "areas_help").
AREAS_HELP = META.get("areas_help") or (open(f"{PROMPTS}/areas.txt").read().strip() if os.path.exists(f"{PROMPTS}/areas.txt") else "")
PROJECT = prompt("project", areas=AREAS_HELP)
REVIEW = prompt("reviewer")                                        # the same review instructions in A and B
BASH = {"name": "bash", "description": "Run a shell command in the repository and return its exit code and combined output (truncated).",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}
DISPATCH = {"name": "dispatch", "description": "Hand one piece of work to a specialist subagent for one area. It starts with no knowledge of this conversation: "
            "write everything it needs in `task`. It works in the same repository and returns a short report when it stops.",
            "input_schema": {"type": "object", "properties": {"area": {"type": "string", "enum": AREAS}, "task": {"type": "string"}}, "required": ["area", "task"]}}
REVIEWTOOL = {"name": "review", "description": "Ask the reviewer subagent to review the current diff of the working copy. It returns its findings; it does not edit files.",
              "input_schema": {"type": "object", "properties": {}, "required": []}}

T0 = time.monotonic()
R = {"run": RUN_ID, "case": META["id"], "config": CONFIG, "model": MODEL, "outcome": "max_tool_calls", "model_calls": 0, "tool_calls": 0,
     "tool_errors": 0, "in_tok": 0, "cache_write": 0, "cache_read": 0, "out_tok": 0, "model_s": 0.0, "tool_s": 0.0,
     "roles": [], "commands": [], "dispatches": [], "reviews": 0, "final_text": ""}

class Stop(Exception):
    """A limit of the attempt was reached, or the model path failed: every agent of the attempt stops."""

def left():
    return MAX_SECONDS - (time.monotonic() - T0)

def bash(cmd, role):
    limit = max(1, min(600, left()))
    t = time.monotonic()
    try:
        p = subprocess.run(["bash", "-o", "pipefail", "-c", cmd], cwd=WD, capture_output=True, text=True, timeout=limit)
        out, rc = (p.stdout + p.stderr), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"command timed out after {limit:.0f} s", 124
    if len(out) > 10000: out = out[:5000] + "\n[... truncated ...]\n" + out[-5000:]
    dt = time.monotonic() - t
    R["tool_calls"] += 1; R["tool_s"] += dt; R["tool_errors"] += rc != 0
    R["commands"].append({"role": role, "cmd": cmd[:400], "rc": rc, "s": round(dt, 2)})
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

def changed():
    out = subprocess.run("git status --short | head -40", shell=True, cwd=REPO, capture_output=True, text=True).stdout.strip()
    return out or "(no file changed)"

class Session:
    """One model conversation with its own context. `handlers` maps a tool name to a function(input) -> text."""
    def __init__(self, client, role, system, tools, handlers):
        self.client, self.role, self.system, self.tools, self.handlers = client, role, system, tools, handlers
        self.messages = []
        self.use = {"role": role, "model_calls": 0, "tool_calls": 0, "in_tok": 0, "cache_write": 0, "cache_read": 0, "out_tok": 0, "s": 0.0}
        R["roles"].append(self.use)

    def run(self, user_text):
        """Send a user message and loop until the model ends its turn. Returns its last text. Raises Stop on a limit."""
        t_in = time.monotonic()
        self.messages.append({"role": "user", "content": user_text})
        try:
            while True:
                if R["tool_calls"] >= MAX_TOOL_CALLS: R["outcome"] = "max_tool_calls"; raise Stop()
                if left() <= 10: R["outcome"] = "timeout"; raise Stop()
                t = time.monotonic()
                try:
                    resp = self.client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=self.system, tools=self.tools,
                                                       messages=with_cache_mark(self.messages), timeout=min(300, left()))
                except Exception as e:
                    why = model_call_failure(e)
                    if why is None: raise
                    R["outcome"] = why; R["error"] = f"{type(e).__name__}: {str(e)[:300]}"; raise Stop()
                R["model_s"] += time.monotonic() - t; R["model_calls"] += 1; self.use["model_calls"] += 1
                u = resp.usage
                for k, v in (("in_tok", u.input_tokens), ("out_tok", u.output_tokens), ("cache_write", u.cache_creation_input_tokens or 0), ("cache_read", u.cache_read_input_tokens or 0)):
                    R[k] += v; self.use[k] += v
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
                    h = self.handlers.get(b.name)
                    self.use["tool_calls"] += 1
                    try:
                        out = h(b.input) if h else f"unknown tool {b.name}"
                    except Stop:
                        # a subagent hit a limit: record the pending results so the history stays well-formed, then stop
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": "stopped: a limit of the attempt was reached", "is_error": True})
                        self.messages.append({"role": "user", "content": results}); raise
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
                self.messages.append({"role": "user", "content": results})
        finally:
            self.use["s"] = round(self.use["s"] + time.monotonic() - t_in, 2)

def task_text():
    cmds = META.get("test_cmds") or [META.get("test_cmd", "")]
    return (f"Task:\n{META['statement']}\n\nTests that must pass when you are done (run from {WD}):\n" + "\n".join(cmds) +
            f"\n\nTheir output on the current code:\n{FAILURE}")

def run_single(client):
    s = Session(client, "single", PROJECT + "\n\n" + prompt("single"), [BASH], {"bash": lambda i: bash(str(i.get("command", "")), "single")})
    R["final_text"] = s.run(task_text())[:2000]
    R["reviews"] += 1
    review = s.run(REVIEW + "\n\nYou wrote this change yourself: review it now, in this session, by these instructions. Report your findings; do not edit files in this step.")
    R["review_text"] = review[:2000]
    R["final_text"] = s.run("Fix every problem your review found, re-run the tests, and finish. If it found none, say so and finish.")[:2000]

def run_team(client):
    def sub(role, system, text):
        return Session(client, role, PROJECT + "\n\n" + system, [BASH], {"bash": lambda i: bash(str(i.get("command", "")), role)}).run(text)

    def dispatch(i):
        area = str(i.get("area", "")); task = str(i.get("task", ""))
        if area not in AREAS: return f"unknown area {area!r}; choose one of {', '.join(AREAS)}"
        R["tool_calls"] += 1
        n = len(R["dispatches"]) + 1
        d = {"n": n, "area": area, "task_chars": len(task), "task": task[:6000]}
        R["dispatches"].append(d)
        try:
            report = sub(f"sub-{area}-{n}", prompt("subagent", area=area), task)
        finally:
            d["files_after"] = changed()[:1500]
        d["report"] = report[:3000]
        return f"Report of the {area} subagent:\n{report[:3000]}\n\nFiles changed in the working copy now:\n{changed()}"

    def review(_i):
        R["tool_calls"] += 1; R["reviews"] += 1
        diff = subprocess.run("git add -A -N . && git diff --stat | tail -30", shell=True, cwd=REPO, capture_output=True, text=True).stdout
        report = sub(f"reviewer-{R['reviews']}", REVIEW, f"Task that the change must solve:\n{META['statement']}\n\nThe change is in the working copy (see `git diff`). Summary:\n{diff}\n\nReport your findings; do not edit files.")
        R["review_text"] = report[:2000]
        return f"Reviewer's report:\n{report[:3000]}"

    o = Session(client, "orchestrator", PROJECT + "\n\n" + prompt("orchestrator", areas=", ".join(AREAS)), [BASH, DISPATCH, REVIEWTOOL],
                {"bash": lambda i: bash(str(i.get("command", "")), "orchestrator"), "dispatch": dispatch, "review": review})
    R["final_text"] = o.run(task_text())[:2000]
    if R["reviews"] == 0:      # the review step is part of both configurations: run it once if the orchestrator skipped it
        R["forced_review"] = True
        R["final_text"] = o.run(review({}) + "\n\nHave every problem in this report fixed by dispatching the work, then finish. If it found none, say so and finish.")[:2000]

def main():
    subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/snapshot/", f"{REPO}/"], check=True)
    if os.path.isdir(f"{CASE}/overlay"):       # dependencies and build products of the preparation, excluded from the diff
        subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", f"{CASE}/overlay/", f"{REPO}/"], check=True)
    if os.path.exists(f"{CASE}/overlay.list"):
        with open(f"{REPO}/.git/info/exclude", "a") as x: x.write(open(f"{CASE}/overlay.list").read())
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key="held-by-the-gateway",
                                 default_headers={"x-run-token": RUN_TOKEN}, max_retries=0)
    try:
        (run_single if CONFIG == "A" else run_team)(client)
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
