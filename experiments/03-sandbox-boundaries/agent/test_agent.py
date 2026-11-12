#!/usr/bin/env python3
"""Offline test of the agent's harness and the runner's report picker. No model, no cluster, no third-party code:
the "task" is a synthetic folder made here, and the model is a stub that returns two scripted answers.
 1. result.py: the report is the last RESULT line that carries the runner's nonce; any other RESULT line is rejected.
 2. selfcheck.py on the synthetic folder: pipefail, the nonce kept out of the commands' environment, a timeout that
    kills the whole process group, a background child that neither holds the call open nor survives it, a report that
    runs nothing from the workspace's git config (with a control showing the trap fires the old way), a FIFO left out.
    The checks that need the harness to be PID 1 of a pod (reading /proc/1, a setsid child) do not apply here.
 3. agent.py end to end with the stub model: the RESULT line carries the nonce, the recorded exit code of
    `false | tail` is not 0, and the patch is the workspace's change."""
import io, json, os, shutil, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ok = True
def check(name, cond, detail):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), name, *(() if "--short" in sys.argv else ("-", detail)), flush=True)

from result import pick
good = {"outcome": "finished", "patch": "P"}
log = "\n".join(["starting", 'RESULT {"outcome": "finished", "patch": "no nonce"}', 'RESULT wrong-nonce {"outcome": "finished", "patch": "wrong"}',
                 'RESULT n0nce {"outcome": "error", "patch": "first"}', "RESULT n0nce {not json", "RESULT n0nce " + json.dumps(good), 'RESULT n0nce "a string"', "RESULTS are in"])
r = pick(log, "n0nce")
check("1a the report is the last line with the runner's nonce", r["patch"] == "P" and r["report_lines_rejected"] == 5, f"picked patch {r['patch']!r}, other RESULT lines rejected: {r['report_lines_rejected']}")
r = pick('RESULT {"outcome": "finished", "patch": "spoofed"}\nRESULT other {"outcome": "finished", "patch": "x"}', "n0nce")
check("1b no line with the nonce: no result", r["outcome"] == "no_result" and r["patch"] == "" and r["report_lines_rejected"] == 2, f"outcome {r['outcome']}, rejected {r['report_lines_rejected']}")
r = pick('RESULT  {"outcome": "finished", "patch": "x"}', "")
check("1c an empty nonce matches nothing", r["outcome"] == "no_result", f"outcome {r['outcome']}")

tmp = tempfile.mkdtemp(prefix="agent-test-"); task = f"{tmp}/task"
os.makedirs(f"{task}/pkg"); os.makedirs(f"{task}/tests")
open(f"{task}/pkg/mod.py", "w").write("def answer():\n    return 41\n")
open(f"{task}/tests/test_mod.py", "w").write("from pkg.mod import answer\n\ndef test_answer():\n    assert answer() == 42\n")
open(f"{task}/.gitignore", "w").write("__pycache__/\n")
env = dict(os.environ, TASK_REPO=task, WORK_REPO=f"{tmp}/work-selfcheck", RESULT_NONCE="n0nce", RUN_ID="offline")
p = subprocess.run([sys.executable, f"{HERE}/selfcheck.py"], env=env, capture_output=True, text=True, timeout=120)
line = next((l for l in p.stdout.splitlines() if l.startswith("SELFCHECK ")), None)
sc = json.loads(line[10:]) if line else {"checks": [], "failed": ["no SELFCHECK line: " + p.stderr[-300:]]}
for c in sc["checks"]:
    if c["ok"] is None: print("n/a ", "2 " + c["check"], "-", c["detail"])
    else: check("2 " + c["check"], c["ok"], c["detail"])
applies = [c for c in sc["checks"] if c["ok"] is not None]
check("2 the self-check ran and its own report carries the nonce", len(applies) >= 7 and not sc["failed"] and pick(p.stdout, "n0nce")["outcome"] == "selfcheck",
      f"{len(applies)} checks apply here, failed: {sc['failed']}, picked outcome: {pick(p.stdout, 'n0nce')['outcome']}")

# 3. the agent loop itself, with a stub in place of the SDK
os.environ.update(TASK_REPO=task, WORK_REPO=f"{tmp}/work-agent", RESULT_NONCE="n0nce-2", RUN_ID="offline-e2e", GATEWAY_URL="http://stub.invalid")
B = types.SimpleNamespace
script = [B(content=[B(type="tool_use", id="t1", input={"command": "printf 'def answer():\\n    return 42\\n' > pkg/mod.py; false | tail -1; echo \"nonce in env: ${RESULT_NONCE:-none}\""}),
                     B(type="tool_use", id="t2", input={"command": "false | tail -1"})], stop_reason="tool_use", usage=B(input_tokens=10, output_tokens=5)),
          B(content=[B(type="text", text="fixed")], stop_reason="end_turn", usage=B(input_tokens=20, output_tokens=5))]
sent = []
class Stub:
    def __init__(self, **kw): self.messages = self
    def create(self, **kw): sent.append(kw["messages"][-1]); return script[len(sent) - 1]
sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=Stub)
import agent
buf, real = io.StringIO(), sys.stdout; sys.stdout = buf
try: agent.main()
finally: sys.stdout = real
r = pick(buf.getvalue(), "n0nce-2"); tool_out = sent[1]["content"][0]["content"] if len(sent) > 1 else ""
check("3a the agent's RESULT line carries the nonce, and only the nonce'd line is picked", r.get("outcome") == "finished" and r.get("model_calls") == 2 and pick(buf.getvalue(), "n0nce")["outcome"] == "no_result",
      f"outcome {r.get('outcome')}, model calls {r.get('model_calls')}; with another nonce: {pick(buf.getvalue(), 'n0nce')['outcome']}")
rcs = [c["rc"] for c in r.get("commands", [])]
check("3b the recorded exit code of `false | tail -1` is not 0", rcs == [0, 1] and "exit code 1" in sent[1]["content"][1]["content"], f"recorded exit codes {rcs} (the first command ends with an echo; the second is the pipeline alone)")
check("3c the command did not see the nonce", "nonce in env: none" in tool_out and "RESULT_NONCE" not in os.environ, f"tool output: {tool_out.strip().splitlines()[-1] if tool_out.strip() else tool_out!r}")
want = "-    return 41\n+    return 42\n"
check("3d the patch is the workspace's change against the frozen folder", want in r.get("patch", "") and r["patch"].count("diff --git") == 1 and "a/pkg/mod.py" in r["patch"],
      f"files in the patch: {r.get('patch', '').count('diff --git')}, change present: {want in r.get('patch', '')}" + (f", error: {r['patch_error']}" if "patch_error" in r else ""))
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
