#!/usr/bin/env python3
"""Offline tests of agent.py with a scripted model (no network, no key): python3 agent/test_agent.py
Each scenario runs the agent in a subprocess against a throwaway snapshot; the fake `anthropic` module answers from a
list of scripted turns, in call order, and records the system prompt and the first user message of every call."""
import json, os, pathlib, subprocess, sys, tempfile, types

HERE = pathlib.Path(__file__).resolve().parent

if os.environ.get("FAKE_SCRIPT"):      # child: install the fake SDK, then run the agent
    script = json.load(open(os.environ["FAKE_SCRIPT"])); seen = []
    class Block:
        def __init__(self, d): self.__dict__.update(d)
        def model_dump(self, exclude_none=True): return dict(self.__dict__)
    class Err(Exception):
        def __init__(self, status, msg): super().__init__(msg); self.status_code = status; self.body = msg
    class Messages:
        def create(self, **kw):
            turn = script.pop(0)
            seen.append({"system": kw["system"][-60:], "n_messages": len(kw["messages"]), "tools": [t["name"] for t in kw["tools"]],
                         "first_user": str(kw["messages"][0]["content"])[:80]})
            json.dump(seen, open(os.environ["FAKE_SEEN"], "w"))
            if "error" in turn: raise Err(*turn["error"])
            blocks = [Block({"type": "text", "text": turn.get("text", "")})] if turn.get("text") else []
            for k, (name, inp) in enumerate(turn.get("tools", [])):
                blocks.append(Block({"type": "tool_use", "id": f"t{len(seen)}_{k}", "name": name, "input": inp}))
            usage = types.SimpleNamespace(input_tokens=100, output_tokens=20, cache_creation_input_tokens=10, cache_read_input_tokens=50)
            return types.SimpleNamespace(content=blocks, usage=usage, stop_reason="tool_use" if turn.get("tools") else turn.get("stop", "end_turn"))
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda **kw: types.SimpleNamespace(messages=Messages())
    fake.APIConnectionError = type("APIConnectionError", (Exception,), {})
    sys.modules["anthropic"] = fake
    sys.path.insert(0, str(HERE))
    import agent
    agent.main()
    sys.exit(0)


def run(config, turns, **env):
    d = pathlib.Path(tempfile.mkdtemp())
    case = d / "cases" / "t1"; snap = case / "snapshot"; snap.mkdir(parents=True)
    (snap / "lib.txt").write_text("old\n")
    g = dict(cwd=snap, check=True, capture_output=True)
    subprocess.run(["git", "init", "-q"], **g); subprocess.run(["git", "add", "-A"], **g)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "snapshot"], **g)
    (case / "meta.json").write_text(json.dumps({"id": "t1", "statement": "Make lib.txt say new.", "test_cmds": ["grep -q new lib.txt"], "areas_help": "Areas: flutter."}))
    (case / "failure.txt").write_text("FAILED: lib.txt says old")
    (d / "script.json").write_text(json.dumps(turns))
    e = {**os.environ, "FAKE_SCRIPT": str(d / "script.json"), "FAKE_SEEN": str(d / "seen.json"), "CASES_ROOT": str(d / "cases"), "CASE_ID": "t1",
         "REPO_DIR": str(d / "repo"), "RUN_ID": "r1", "RUN_TOKEN": "tok", "GATEWAY_URL": "http://x", "PROMPT_DIR": str(HERE), "CONFIG": config, **{k: str(v) for k, v in env.items()}}
    out = subprocess.run([sys.executable, __file__], env=e, capture_output=True, text=True)
    line = [l for l in out.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, out.stdout + out.stderr
    return json.loads(line[-1][7:]), json.load(open(d / "seen.json"))


B = lambda cmd: ("bash", {"command": cmd})
ok = 0
def check(name, cond, detail=""):
    global ok
    if not cond: print(f"FAIL {name} {detail}"); sys.exit(1)
    ok += 1

# 1. A: work, done, review in the same session, fix step
r, seen = run("A", [{"tools": [B("echo new > lib.txt")]}, {"text": "done"}, {"text": "review: no problems"}, {"text": "nothing to fix"}])
check("A outcome", r["outcome"] == "finished", r)
check("A patch", "+new" in r["patch"]); check("A one session", [x["role"] for x in r["roles"]] == ["single"])
check("A review in the same session", seen[2]["n_messages"] == 5 and r["reviews"] == 1, seen)
check("A counts", (r["model_calls"], r["tool_calls"], r["in_tok"], r["cache_read"]) == (4, 1, 400, 200), r)
check("A tools", seen[0]["tools"] == ["bash"])

# 2. B: orchestrator reads, dispatches, subagent edits, review by a fresh reviewer
r, seen = run("B", [{"tools": [B("cat lib.txt")]}, {"tools": [("dispatch", {"area": "flutter", "task": "Change lib.txt to say new. Test: grep -q new lib.txt"})]},
                    {"tools": [B("echo new > lib.txt")]}, {"text": "changed lib.txt"}, {"tools": [("review", {})]},
                    {"tools": [B("git diff")]}, {"text": "no problems found"}, {"text": "team done"}])
check("B outcome", r["outcome"] == "finished", r)
check("B roles", [x["role"] for x in r["roles"]] == ["orchestrator", "sub-flutter-1", "reviewer-1"], r["roles"])
check("B patch", "+new" in r["patch"]); check("B tool calls", r["tool_calls"] == 5, r["tool_calls"])
check("B subagent has its own context", seen[2]["n_messages"] == 1 and "Change lib.txt" in seen[2]["first_user"] and seen[2]["tools"] == ["bash"], seen[2])
check("B reviewer has its own context", seen[5]["n_messages"] == 1 and "Task that the change" in seen[5]["first_user"], seen[5])
check("B orchestrator tools", seen[0]["tools"] == ["bash", "dispatch", "review"])
check("B same project notes", "Task:" in seen[0]["first_user"] and r["reviews"] == 1 and not r.get("forced_review"))

# 3. B: the orchestrator ends without a review -> one forced review, report handed back once
r, seen = run("B", [{"tools": [("dispatch", {"area": "rules", "task": "do it"})]}, {"text": "sub report"}, {"text": "done, no review"},
                    {"text": "reviewer: one problem"}, {"text": "handled"}])
check("B forced review", r["outcome"] == "finished" and r["forced_review"] and r["reviews"] == 1 and [x["role"] for x in r["roles"]][-1] == "reviewer-1", r)

# 4. the tool-call limit is for the whole team
r, seen = run("B", [{"tools": [B("true")]}, {"tools": [("dispatch", {"area": "flutter", "task": "x"})]}, {"tools": [B("echo new > lib.txt")]}, {"tools": [B("true")]}], MAX_TOOL_CALLS=3)
check("limit", r["outcome"] == "max_tool_calls" and r["tool_calls"] == 3 and "+new" in r["patch"], r)

# 5. this run's budget ends the attempt as an outcome, with the patch so far; another 429 is infrastructure, no patch
r, _ = run("A", [{"tools": [B("echo new > lib.txt")]}, {"error": [429, "run budget: this call reserves $0.05, $0.01 left in run r1"]}])
check("budget", r["outcome"] == "budget_exhausted" and "+new" in r["patch"], r)
r, _ = run("A", [{"tools": [B("echo new > lib.txt")]}, {"error": [429, "total budget reached"]}])
check("gateway", r["outcome"] == "gateway_unavailable" and r["patch"] == "", r)

# 6. an unknown area is answered, not executed; a failing command counts as a tool error
r, _ = run("B", [{"tools": [("dispatch", {"area": "ios", "task": "x"})]}, {"tools": [B("false")]}, {"tools": [("review", {})]}, {"text": "ok"}, {"text": "done"}])
check("unknown area", r["dispatches"] == [] and r["tool_errors"] == 1 and r["outcome"] == "finished", r)
# a commit made by the agent does not hide its patch: the diff is against the snapshot's commit (24/11/2026, external review)
r, _ = run("A", [{"tools": [B("echo new > lib.txt && git add -A && git -c user.name=a -c user.email=a@a commit -qm wip")]}, {"text": "done"}, {"text": "review: no problems"}, {"text": "nothing to fix"}])
check("agent's own commit", r["outcome"] == "finished" and "+new" in r["patch"], r)
print(f"{ok} checks passed")
