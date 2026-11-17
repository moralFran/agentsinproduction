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
run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r$rep"; out="$base/attempts-$round.jsonl"; pd="$base/patches/$round"
# Tries that never became an attempt (the model path was unavailable, or the run opened without a usable token) are
# kept here, not in the journal: they are redone on resume. The gateway refuses a reused run id, so a redo gets a new
# one (-t2, -t3). After MAX_INFRA_TRIES such tries the script stops and asks for a person.
# "Unavailable" is the pod's own word, and the pod ran commands a model chose. It is accepted only when something
# outside the pod agrees: the gateway booked at least one failed model call to this run (model_path_failures in the
# close reply), or the runner's own close of the run was never confirmed. Otherwise the try IS an attempt: it goes to
# the journal as an error, without a patch, and is not redone (added 2026-11-13).
infra="$base/infra-$round.jsonl"
# A recorded attempt is complete for round scheduling, including a recorded failure. Never spend or overwrite it.
# Parse the journal rather than depending on JSON whitespace; malformed records still stop the runner.
recorded=$(python3 - "$out" "$run0" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []
print("yes" if any(row.get("run") == sys.argv[2] or str(row.get("run", "")).startswith(sys.argv[2] + "-t") for row in rows) else "no")
PY
)
[ "$recorded" = yes ] && { echo "run $run0 already recorded; skipping"; exit 0; }
tries=$(python3 - "$infra" "$run0" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []
print(sum(1 for row in rows if row.get("run") == sys.argv[2] or str(row.get("run", "")).startswith(sys.argv[2] + "-t")))
PY
)
[ "$tries" -ge "${MAX_INFRA_TRIES:-3}" ] && { echo "run $run0 already failed $tries times for infrastructure reasons ($infra): look at it before trying again" >&2; exit 1; }
if [ "$tries" = 0 ]; then run="$run0"; else run="$run0-t$((tries + 1))"; fi
not_an_attempt() {   # $1 = reason, $2 = file with the agent's output or "", $3 = file with the gateway's close reply or ""
  python3 - "$round" "$cid" "$rep" "$run" "$1" "${2:-}" "${3:-}" >> "$infra" <<'PY'
import json, os, sys, time
rnd, cid, rep, run, reason, fa, fg = sys.argv[1:]
grab = lambda f, tag: next((json.loads(l[len(tag):]) for l in reversed(open(f).readlines()) if l.startswith(tag)), {}) if f and os.path.exists(f) else {}
agent = grab(fa, "RESULT "); agent.pop("patch", None)
try: gw = json.loads(open(fg).read() or "{}") if fg and os.path.exists(fg) else {}
except ValueError: gw = {}
print(json.dumps({"round": rnd, "case": cid, "rep": int(rep), "run": run, "reason": reason, "at": round(time.time()), "agent": agent,
                  "agent_pod": grab(fa, "POD "), "gateway": {"spent_usd": gw.get("spent_usd"), "calls": gw.get("calls"), "cap_usd": gw.get("cap_usd"),
                                                          "model_path_failures": gw.get("model_path_failures"),
                                                          "model_path_failure_reasons": gw.get("model_path_failure_reasons")}}))
PY
}
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
  not_an_attempt "the gateway opened the run but returned no usable token"
  echo "gateway opened run $run but returned no usable token; the run was closed"; exit 1; }
unset opened
t0=$(date +%s)
case "$round" in v2*) pv=v2;; *) pv=v1;; esac        # agent version: the system prompt template (agent/prompt-<pv>.txt)
RUN_TOKEN="$run_token" python3 cases/pod.py agent "$cid" "ag-$run" 1500 --env PROMPT_FILE="/code/prompt-$pv.txt" --env RUN_ID="$run" --env GATEWAY_URL=http://10.43.210.10:8080 \
  --env MAX_TOOL_CALLS=60 --env MAX_SECONDS=1440 -- /opt/agent-venv/bin/python -u /code/agent.py > "/tmp/$run.agent" 2>&1 || true
unset run_token
# The close revokes the token. If the gateway cannot write it, it answers 503 and halts; try again, and if it never
# confirms, record the attempt (cost unknown) and stop the round at the end: later attempts would only meet a halted gateway.
close_ok=0
for _ in 1 2 3; do
  if admin -X POST "$ADMIN/runs/$run/close" -d '{}' > "/tmp/$run.gw"; then close_ok=1; break; fi
  sleep "${CLOSE_RETRY_S:-2}"
done
[ "$close_ok" = 1 ] || echo '{}' > "/tmp/$run.gw"
agent_outcome=$(python3 - "/tmp/$run.agent" "$pd/$run.diff" <<'PY'
import json, sys
res = next((json.loads(l[7:]) for l in reversed(open(sys.argv[1]).readlines()) if l.startswith("RESULT ")), {"outcome": "no_result", "patch": ""})
open(sys.argv[2], "w").write(res.get("patch", ""))
print(res.get("outcome"))
PY
)
# The pod never reached its main container (the network gate failed or timed out, cases/pod.py): the agent did not
# run, so there is no attempt to record. This is the runner's own reading of the init container's log, which ran
# before any command a model chose. Kept in the infra file and redone under a new run id (added 2026-11-13).
pod_infra=$(python3 -c 'import json,sys
row = next((json.loads(l[4:]) for l in reversed(open(sys.argv[1]).readlines()) if l.startswith("POD ")), {})
print(str(row.get("infra_error") or "")[:400])' "/tmp/$run.agent" 2>/dev/null || true)
if [ -n "$pod_infra" ] && [ "$agent_outcome" = no_result ]; then
  not_an_attempt "the agent's pod did not start its main container: $pod_infra" "/tmp/$run.agent" "/tmp/$run.gw"
  rm -f "$pd/$run.diff" "/tmp/$run".*
  echo "run $run: the agent's pod did not start ($pod_infra); not recorded as an attempt (see $infra), the resume redoes it" >&2
  exit 1
fi
unconfirmed=0
if [ "$agent_outcome" = gateway_unavailable ]; then
  failed_calls=$(python3 -c 'import json,sys
try: n = json.load(open(sys.argv[1])).get("model_path_failures", 0)
except Exception: n = 0
print(n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 0)' "/tmp/$run.gw")
  if [ "$failed_calls" -gt 0 ] || [ "$close_ok" != 1 ]; then
    # The agent did not get its model calls (gateway halted, run closed, provider error) and the gateway, or the
    # runner's own failed close, says so too: infrastructure, not a result. Nothing is validated and nothing enters
    # the journal, so the resume redoes this case/repetition under a new run id.
    if [ "$failed_calls" -gt 0 ]; then why="the model path was unavailable to the agent (the gateway booked $failed_calls failed call(s) to the run)"
    else why="the model path was unavailable to the agent (the runner could not close the run either)"; fi
    not_an_attempt "$why" "/tmp/$run.agent" "/tmp/$run.gw"
    rm -f "$pd/$run.diff" "/tmp/$run".*
    echo "run $run: the model path was unavailable (see $infra); not recorded as an attempt, the resume redoes it" >&2
    exit 1
  fi
  # Nothing outside the pod confirms it: recorded as an attempt that ended in an error, with no patch.
  unconfirmed=1; : > "$pd/$run.diff"
  echo "run $run: the pod reported the model path as unavailable, but the gateway booked no failed call to this run; recorded as an attempt (error)" >&2
fi
python3 cases/validate.py "$cid" "$pd/$run.diff" "va-$run" > "/tmp/$run.exec" 2>&1 || true
python3 - "$round" "$cid" "$rep" "$run" "$t0" "/tmp/$run.agent" "/tmp/$run.gw" "/tmp/$run.exec" "$unconfirmed" >> "$out" <<'PY'
import json, sys, time
rnd, cid, rep, run, t0, fa, fg, fe, unconfirmed = sys.argv[1:]
grab = lambda f, tag: next((json.loads(l[len(tag):]) for l in reversed(open(f).readlines()) if l.startswith(tag)), {})
agent = grab(fa, "RESULT "); agent.pop("patch", None); apod = grab(fa, "POD "); ex = grab(fe, "EXECUTOR "); epod = grab(fe, "POD ")
if unconfirmed == "1":      # the pod's "gateway_unavailable" had no confirmation outside the pod (see the top of this file)
    agent.update(outcome="error", claimed_outcome="gateway_unavailable",
                 error="reported gateway_unavailable, but the gateway booked no failed model call to this run; its own account: " + str(agent.get("error", ""))[:300])
gw = json.loads(open(fg).read() or "{}")
print(json.dumps({"round": rnd, "case": cid, "rep": int(rep), "run": run, "agent": agent or {"outcome": "no_result"}, "agent_pod": apod,
                  "gateway": {"spent_usd": gw.get("spent_usd"), "calls": gw.get("calls"), "cap_usd": gw.get("cap_usd"),
                              "model_path_failures": gw.get("model_path_failures")},
                  "executor": ex, "executor_pod": epod, "wall_s": round(time.time() - int(t0), 1)}))
PY
rm -f "/tmp/$run".*
tail -1 "$out" | python3 -c 'import json,sys; r=json.load(sys.stdin); a=r["agent"]; print(r["run"], "agent:", a.get("outcome"), "tools", a.get("tool_calls"), "calls", a.get("model_calls"), "| gateway $", r["gateway"]["spent_usd"], "| executor:", r["executor"].get("outcome"), r["executor"].get("why", "")[:80])'
[ "$close_ok" = 1 ] || { echo "the gateway did not confirm the close of run $run (recorded with unknown cost): make its state writable, close the run again, then resume the round" >&2; exit 1; }
