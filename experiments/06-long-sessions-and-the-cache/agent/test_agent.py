#!/usr/bin/env python3
"""Offline tests of agent.py (experiment 06, V7: L0 and L2) with a scripted model (no network, no key): python3 agent/test_agent.py
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
            last = kw["messages"][-1]["content"]; last = last if isinstance(last, list) else [{"type": "text", "text": last}]
            seen.append({"system_head": kw["system"][:40], "system": kw["system"], "n_messages": len(kw["messages"]), "tools": [t["name"] for t in kw["tools"]],
                         "first_user": (lambda c: c if isinstance(c, str) else " ".join(b.get("text", "") for b in c))(kw["messages"][0]["content"])[:400], "last_types": [b["type"] for b in last],
                         "last_text": (last[-1].get("text") or "")[:200], "marked": "cache_control" in last[-1],
                         "results": [b.get("content") for b in last if b.get("type") == "tool_result"]})
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


def run(compact, turns, guide="# Guide\nRule one.\n", **env):
    d = pathlib.Path(tempfile.mkdtemp())
    case = d / "cases" / "t1"; snap = case / "snapshot"; snap.mkdir(parents=True)
    (snap / "lib.txt").write_text("old\n")
    if guide is not None: (snap / "CLAUDE.md").write_text(guide)
    g = dict(cwd=snap, check=True, capture_output=True)
    subprocess.run(["git", "init", "-q"], **g); subprocess.run(["git", "add", "-A"], **g)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "snapshot"], **g)
    (case / "meta.json").write_text(json.dumps({"id": "t1", "statement": "Make lib.txt say new.", "test_cmds": ["grep -q new lib.txt"], "areas_help": "Areas: flutter."}))
    (case / "failure.txt").write_text("FAILED: lib.txt says old")
    (d / "script.json").write_text(json.dumps(turns))
    e = {**os.environ, "FAKE_SCRIPT": str(d / "script.json"), "FAKE_SEEN": str(d / "seen.json"), "CASES_ROOT": str(d / "cases"), "CASE_ID": "t1",
         "REPO_DIR": str(d / "repo"), "RUN_ID": "r1", "RUN_TOKEN": "tok", "GATEWAY_URL": "http://x", "PROMPT_DIR": str(HERE), "COMPACT": compact, **{k: str(v) for k, v in env.items()}}
    out = subprocess.run([sys.executable, __file__], env=e, capture_output=True, text=True)
    line = [l for l in out.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, out.stdout + out.stderr
    return json.loads(line[-1][7:]), json.load(open(d / "seen.json"))


B = lambda cmd: ("bash", {"command": cmd})
E = lambda s: ("end_phase", {"summary": s})
ok = 0
def check(name, cond, detail=""):
    global ok
    if not cond: print(f"FAIL {name} {detail}"); sys.exit(1)
    ok += 1

# 1. L0: phases are only recorded; the reminder is appended to request 5 and stays; guide and attempt id in the system
turns = [{"tools": [B("cat lib.txt")]}, {"tools": [E("plan: change lib.txt")]}, {"tools": [B("echo new > lib.txt")]}, {"tools": [B("grep -q new lib.txt")]},
         {"tools": [E("app: done")]}, {"tools": [B("true")]}, {"text": "done"}, {"text": "review: no problems"}, {"text": "nothing to fix"}]
r, seen = run("none", turns)
check("L0 outcome", r["outcome"] == "finished" and "+new" in r["patch"], r)
check("L0 tools", all(x["tools"] == ["bash", "end_phase"] for x in seen), seen[0]["tools"])
check("L0 phases", [p["summary"] for p in r["phases"]] == ["plan: change lib.txt", "app: done"] and r["compactions"] == [], r["phases"])
check("L0 attempt id first", seen[0]["system_head"].startswith("Attempt r1."), seen[0]["system_head"])
check("L0 guide in system", all("Project guide" in x["system"] and "Rule one." in x["system"] for x in seen))
check("L0 same system every call", len({x["system"] for x in seen}) == 1)
check("L0 reminder at call 5", r["reminder_call"] == 5 and seen[4]["last_text"].startswith("Reminder: run") and seen[4]["last_types"][-1] == "text"
      and seen[4]["last_types"][0] == "tool_result" and seen[4]["marked"], seen[4])
check("L0 reminder kept", seen[5]["n_messages"] == seen[4]["n_messages"] + 2, (seen[4]["n_messages"], seen[5]["n_messages"]))
check("L0 history only grows", [x["n_messages"] for x in seen] == sorted(x["n_messages"] for x in seen))
check("L0 per-call log", len(r["calls"]) == r["model_calls"] == 9 and r["calls"][0]["prompt"] == 160 and r["tool_calls"] == 6, r["calls"][0])

# 2. L2: after end_phase, one summary call with the fixed prompt, then the history is [task + summary]
turns = [{"tools": [B("cat lib.txt")]}, {"tools": [E("plan: change lib.txt")]}, {"text": "SUMMARY: lib.txt must say new; nothing changed yet."},
         {"tools": [B("echo new > lib.txt")]}, {"tools": [E("app: done")]}, {"text": "SUMMARY: lib.txt changed; tests pass."},
         {"text": "done"}, {"text": "review: no problems"}, {"text": "nothing to fix"}]
r, seen = run("phase", turns)
check("L2 outcome", r["outcome"] == "finished" and "+new" in r["patch"], r)
check("L2 two compactions", len(r["compactions"]) == 2 and [c["at_call"] for c in r["compactions"]] == [3, 6], r["compactions"])
check("L2 summary request", seen[2]["last_text"].startswith("Your context is about to be replaced") and seen[2]["last_types"][0] == "tool_result", seen[2])
check("L2 history replaced", seen[3]["n_messages"] == 1 and seen[3]["first_user"].startswith("Task:") and "SUMMARY: lib.txt must say new" in seen[3]["first_user"], seen[3])
check("L2 same system and tools", len({x["system"] for x in seen}) == 1 and all(x["tools"] == ["bash", "end_phase"] for x in seen))
check("L2 summary call counted", [c["role"] for c in r["calls"]].count("compact") == 2 and r["model_calls"] == 9, [c["role"] for c in r["calls"]])
check("L2 prompt before recorded", r["compactions"][0]["prompt_before"] == 160)

# 3. L2: a summary call that answers only with a tool call falls back to the end_phase summaries
r, seen = run("phase", [{"tools": [E("plan: change lib.txt")]}, {"tools": [B("true")]}, {"tools": [B("echo new > lib.txt")]}, {"text": "done"},
                        {"text": "review ok"}, {"text": "fine"}])
check("L2 fallback", r["compactions"][0].get("fallback") == "end_phase summaries" and "plan: change lib.txt" in seen[2]["first_user"], (r["compactions"], seen[2]))

# 4. limits and the gateway: this run's budget ends the attempt as an outcome with the patch; another 429 is infrastructure
r, _ = run("none", [{"tools": [B("echo new > lib.txt")]}, {"error": [429, "run budget: this call reserves $0.05, $0.01 left in run r1"]}])
check("budget", r["outcome"] == "budget_exhausted" and "+new" in r["patch"], r)
r, _ = run("none", [{"tools": [B("echo new > lib.txt")]}, {"error": [429, "total budget reached"]}])
check("gateway", r["outcome"] == "gateway_unavailable" and r["patch"] == "", r)
r, _ = run("none", [{"tools": [B("true")]}, {"tools": [B("echo new > lib.txt")]}, {"tools": [B("true")]}], MAX_TOOL_CALLS=2)
check("tool-call limit", r["outcome"] == "max_tool_calls" and r["tool_calls"] == 2 and "+new" in r["patch"], r)
r, seen = run("none", [{"text": "done"}, {"text": "ok"}, {"text": "ok"}], guide=None)
check("no guide", "(the repository has no CLAUDE.md)" in seen[0]["system"] and r["outcome"] == "finished")
# 5. a command whose output is not valid UTF-8 (a byte cut in the middle of a character) does not crash the harness:
#    the bad byte becomes U+FFFD, valid text is passed as before, newlines as before (added 23/11, after v1-t8-l2-r2)
r, seen = run("none", [{"tools": [B(r"printf 'caf\xe2\x28 ok\n'; printf 'caf\xc3\xa9 \xe2\x80\x94 a\r\nb\n' >&2")]}, {"tools": [B("echo new > lib.txt")]},
                       {"text": "done"}, {"text": "ok"}, {"text": "ok"}])
check("invalid UTF-8 output", r["outcome"] == "finished" and "+new" in r["patch"], r)
check("invalid UTF-8 replaced, valid kept", seen[1]["results"] == ["exit code 0\ncaf\ufffd( ok\ncaf\u00e9 \u2014 a\nb\n"], seen[1]["results"])
print(f"{ok} checks passed")
