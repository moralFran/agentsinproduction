#!/usr/bin/env python3
"""Offline tests of replay.py's transformations on a synthetic recorded trajectory (no network, no key)."""
import copy, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay as R

def trajectory(n=20):
    """n recorded request bodies of an append-only agent loop, with the reminder appended to request 5."""
    sysp = "Attempt smoke-l0-1.\n\nYou are working on a production mobile app."
    tools = [{"name": "bash", "description": "b", "input_schema": {"type": "object"}}, {"name": "end_phase", "description": "e", "input_schema": {"type": "object"}}]
    msgs, out = [{"role": "user", "content": "Task: do it"}], []
    for k in range(1, n + 1):
        if k == 5: msgs[-1]["content"] = msgs[-1]["content"] + [{"type": "text", "text": R.REMINDER}]
        body = {"model": "claude-sonnet-5-5", "max_tokens": 8192, "system": sysp, "tools": tools, "messages": copy.deepcopy(msgs)}
        last = body["messages"][-1]
        if isinstance(last["content"], str): last["content"] = [{"type": "text", "text": last["content"]}]
        last["content"][-1]["cache_control"] = {"type": "ephemeral"}
        out.append(body)
        msgs.append({"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": f"s{k}"}, {"type": "tool_use", "id": f"t{k}", "name": "bash", "input": {"command": "ls"}}]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{k}", "content": "ok"}]})
    return out

T = trajectory(); ok = 0
def check(name, cond, detail=""):
    global ok
    if not cond: print("FAIL", name, detail); sys.exit(1)
    ok += 1
B = lambda cond: [R.transform(cond, k, T[k - 1], "rep-x", T, now="12:00:%02d" % k) for k in range(1, 21)]
strip = lambda b: {**b, "system": b["system"].split(".", 1)[1], "max_tokens": None}

check("points for K=20", R.points(20) == (6, 11, 16))
r0 = B("R0")
check("all: max_tokens 0 and own attempt id", all(b["max_tokens"] == 0 and b["system"].startswith("Attempt rep-x.") for b in r0))
check("R0 = recorded but the id", all(strip(b) == strip(t) for b, t in zip(r0, T)))
check("R0 does not change the recorded bodies", T[0]["system"].startswith("Attempt smoke-l0-1.") and T[0]["max_tokens"] == 8192)
r1 = B("R1"); check("R1 time line, new each request", all(b["system"].endswith("Current time: 12:00:%02d" % k) for k, b in enumerate(r1, 1)) and len({b["system"] for b in r1}) == 20)
r2 = B("R2"); check("R2 tools alternate", [b["tools"][0]["name"] for b in r2[:4]] == ["bash", "end_phase", "bash", "end_phase"])
r3 = B("R3"); check("R3 effort from 11", [("output_config" in b) for b in r3] == [False] * 10 + [True] * 10 and r3[10]["output_config"] == {"effort": "medium"})
check("R4 sleeps before 6, 11, 16", [k for k in range(1, 21) if R.sleeps_before("R4", k, 20)] == [6, 11, 16] and R.sleeps_before("R0", 6, 20) == 0)
r41 = B("R4-1h"); check("R4-1h marks 1h", all(b["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"} for b in r41))
check("R4-1h sleeps too", R.sleeps_before("R4-1h", 11, 20) == 360)
r5 = B("R5")
check("R5 reminder until 10, deleted from 11", [R.reminder_pos(b) is not None for b in r5] == [False] * 4 + [True] * 6 + [False] * 10)
check("R5 deletes only the reminder", all(strip(b)["messages"][:3] == strip(t)["messages"][:3] for b, t in zip(r5[10:], T[10:])) and
      all(len(b["messages"]) == len(t["messages"]) for b, t in zip(r5, T)))
r5d = B("R5-drop"); check("R5-drop adds drop_block from 11", [b.get("thinking") == R.DROP_BLOCK for b in r5d] == [False] * 10 + [True] * 10)
r5s = B("R5-sys"); at = len(T[10]["messages"])
check("R5-sys system message after request 11's user turn", all(b["messages"][at] == {"role": "system", "content": R.NEW_INSTRUCTION} for b in r5s[10:])
      and [sum(m["role"] == "system" for m in b["messages"]) for b in r5s] == [0] * 10 + [1] * 10)
check("R5-sys placement: last at 11, then followed by an assistant turn", r5s[10]["messages"][-1]["role"] == "system" and all(b["messages"][at + 1]["role"] == "assistant" for b in r5s[11:]))
check("R5-sys keeps the reminder", all(R.reminder_pos(b) is not None for b in r5s[4:]))
d = tempfile.mkdtemp(); f = os.path.join(d, "bodies.jsonl")
with open(f, "w") as fh:
    for n, b in enumerate(T, 1): fh.write(json.dumps({"n": n, "status": 200, "body": b}) + "\n")
    fh.write(json.dumps({"n": 21, "status": 429, "body": T[0]}) + "\n")
check("load keeps the first K successful requests in order", R.load(f, 20) == T)
out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay.py"), f, "R5-sys", "--dry"], capture_output=True, text=True)
check("dry run", out.returncode == 0 and len(out.stdout.splitlines()) == 20 and "sys_msgs 1" in out.stdout.splitlines()[10], out.stdout[-300:] + out.stderr[-300:])
print(f"{ok} checks passed")
