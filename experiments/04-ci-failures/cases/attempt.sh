#!/usr/bin/env bash
# Runs ON aip-ci-01. One attempt of the agent on one frozen case, then the executor's mandatory checks on its patch.
#  1. opens a run on the gateway's admin port with the per-attempt cap (US$0.33);
#  2. agent pod (ci-agent, Kata, gateway only, 25 min hard deadline, 60 tool calls) produces a patch;
#  3. closes the run and reads what the gateway booked for it;
#  4. executor pod (ci-exec, Kata, no network) validates the patch.
# Appends one JSON line to results/attempts-<round>.jsonl.   usage: attempt.sh <round-id> <case-id> <rep>
# Smoke test (SMOKE=1, round id smoke-*): the case only needs a "reproduced" verdict (the list is not frozen yet), and
# everything goes to smoke/ instead of results/: smoke attempts are never v1 data.
set -euo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
round="${1:?round}"; cid="${2:?case}"; rep="${3:?rep}"; CAP="${CAP_USD:-0.33}"; ADMIN=http://10.43.210.10:8081
if [ "${SMOKE:-0}" = 1 ]; then
  case "$round" in smoke-*) ;; *) echo "smoke rounds must be named smoke-*"; exit 1;; esac
  grep "\"id\": \"$cid\"" cases/repro.jsonl | grep -q '"verdict": "reproduced"' || { echo "case $cid has no reproduced verdict"; exit 1; }
  base=smoke
else
  grep -q "^$cid," cases/cases.csv 2>/dev/null || { echo "case $cid is not in the frozen cases.csv"; exit 1; }
  base=results
fi
run="$round-$(echo "$cid" | md5sum | cut -c1-8)-r$rep"; out="$base/attempts-$round.jsonl"; pd="$base/patches/$round"
# A recorded attempt is complete for round scheduling, including a recorded failure. Never spend or overwrite it.
# Parse the journal rather than depending on JSON whitespace; malformed records still stop the runner.
recorded=$(python3 - "$out" "$run" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []
print("yes" if any(row.get("run") == sys.argv[2] for row in rows) else "no")
PY
)
[ "$recorded" = yes ] && { echo "run $run already recorded; skipping"; exit 0; }
[ -s "/srv/ci/cases/$cid/failure.txt" ] || { echo "case $cid has no failure.txt (written at the freeze, or by smoke-failure.py)"; exit 1; }
mkdir -p "$pd"
ADMIN_KEY_FILE="${ADMIN_KEY_FILE:-/srv/ci/admin-key}"
[ -s "$ADMIN_KEY_FILE" ] || { echo "missing gateway admin key: run infra/setup-lab.sh" >&2; exit 1; }
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat "$ADMIN_KEY_FILE")" | curl -sf --config - "$@"; }
opened=$(admin -X POST "$ADMIN/runs" -d "{\"run\": \"$run\", \"cap_usd\": $CAP}") || { echo "gateway refused to open run $run"; exit 1; }
# The run exists from here on. If the reply carries no usable token (an older gateway, an unexpected body), close it
# instead of leaving an open run behind.
run_token=$(printf '%s' "$opened" | python3 -c 'import json,sys; token=json.load(sys.stdin)["token"]; assert isinstance(token,str) and len(token)>=32; print(token)') || {
  admin -X POST "$ADMIN/runs/$run/close" -d '{}' >/dev/null || echo "could not close run $run either" >&2
  echo "gateway opened run $run but returned no usable token; the run was closed"; exit 1; }
unset opened
t0=$(date +%s)
case "$round" in v2*) pv=v2;; *) pv=v1;; esac        # agent version: the system prompt template (agent/prompt-<pv>.txt)
RUN_TOKEN="$run_token" python3 cases/pod.py agent "$cid" "ag-$run" 1500 --env PROMPT_FILE="/code/prompt-$pv.txt" --env RUN_ID="$run" --env GATEWAY_URL=http://10.43.210.10:8080 \
  --env MAX_TOOL_CALLS=60 --env MAX_SECONDS=1440 -- /opt/agent-venv/bin/python -u /code/agent.py > "/tmp/$run.agent" 2>&1 || true
unset run_token
admin -X POST "$ADMIN/runs/$run/close" -d '{}' > "/tmp/$run.gw" || echo '{}' > "/tmp/$run.gw"
python3 - "/tmp/$run.agent" "$pd/$run.diff" <<'PY'
import json, sys
res = next((json.loads(l[7:]) for l in reversed(open(sys.argv[1]).readlines()) if l.startswith("RESULT ")), {"outcome": "no_result", "patch": ""})
open(sys.argv[2], "w").write(res.get("patch", ""))
PY
python3 cases/validate.py "$cid" "$pd/$run.diff" "va-$run" > "/tmp/$run.exec" 2>&1 || true
python3 - "$round" "$cid" "$rep" "$run" "$t0" "/tmp/$run.agent" "/tmp/$run.gw" "/tmp/$run.exec" >> "$out" <<'PY'
import json, sys, time
rnd, cid, rep, run, t0, fa, fg, fe = sys.argv[1:]
grab = lambda f, tag: next((json.loads(l[len(tag):]) for l in reversed(open(f).readlines()) if l.startswith(tag)), {})
agent = grab(fa, "RESULT "); agent.pop("patch", None); apod = grab(fa, "POD "); ex = grab(fe, "EXECUTOR "); epod = grab(fe, "POD ")
gw = json.loads(open(fg).read() or "{}")
print(json.dumps({"round": rnd, "case": cid, "rep": int(rep), "run": run, "agent": agent or {"outcome": "no_result"}, "agent_pod": apod,
                  "gateway": {"spent_usd": gw.get("spent_usd"), "calls": gw.get("calls"), "cap_usd": gw.get("cap_usd")},
                  "executor": ex, "executor_pod": epod, "wall_s": round(time.time() - int(t0), 1)}))
PY
rm -f "/tmp/$run".*
tail -1 "$out" | python3 -c 'import json,sys; r=json.load(sys.stdin); a=r["agent"]; print(r["run"], "agent:", a.get("outcome"), "tools", a.get("tool_calls"), "calls", a.get("model_calls"), "| gateway $", r["gateway"]["spent_usd"], "| executor:", r["executor"].get("outcome"), r["executor"].get("why", "")[:80])'
