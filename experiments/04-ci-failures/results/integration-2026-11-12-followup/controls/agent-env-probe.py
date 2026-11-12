#!/usr/bin/env python3
"""Follow-up integration probe (2026-11-12), runs INSIDE a pod of the agent's shape (cases/pod.py build_spec "agent", with
RUN_TOKEN set to a DUMMY value the way pod.py passes the real one). It loads the harness's own /code/agent.py as a module
(its module-level code reads and removes RUN_TOKEN; main() is not called, so no model request is made) and then uses
agent.py's own bash() tool function to ask what a tool command inherits. Prints yes/no and names only, never a value."""
import importlib.util, json, os
out = lambda **kw: print("AGENTENV " + json.dumps(kw), flush=True)
dummy = os.environ.get("RUN_TOKEN", "")
out(step="before loading agent.py", run_token_in_environ="RUN_TOKEN" in os.environ, dummy_length=len(dummy))
os.environ.setdefault("FAILURE_FILE", f"/srv/ci/cases/{os.environ['CASE_ID']}/meta.json")   # any readable file: failure.txt may not exist yet
spec = importlib.util.spec_from_file_location("agent", "/code/agent.py"); agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)
out(step="after loading agent.py", run_token_in_environ="RUN_TOKEN" in os.environ, agent_holds_token=getattr(agent, "RUN_TOKEN", None) == dummy)
rc, text, _ = agent.bash("env | cut -d= -f1 | grep -c '^RUN_TOKEN$'; env | cut -d= -f1 | sort | tr '\\n' ' '", 20)
lines = text.strip().splitlines()
out(step="agent.bash tool command", rc=rc, run_token_variables_in_tool_env=lines[0] if lines else None, tool_env_names=lines[1].split() if len(lines) > 1 else None)
rc, text, _ = agent.bash("env | grep -c -F -- \"$(printf '%s' " + json.dumps(dummy) + ")\"", 20)
out(step="dummy value anywhere in the tool's environment", count=text.strip().splitlines()[0] if text.strip() else None)
# the limitation the code comment documents: a process of the same uid can read the agent process's INITIAL environment
rc, text, _ = agent.bash(f"tr '\\0' '\\n' < /proc/{os.getpid()}/environ | cut -d= -f1 | grep -c '^RUN_TOKEN$'", 20)
out(step="/proc/<agent pid>/environ read by a tool command (documented limitation)", rc=rc, run_token_variable_present=text.strip().splitlines()[0] if text.strip() else None)
