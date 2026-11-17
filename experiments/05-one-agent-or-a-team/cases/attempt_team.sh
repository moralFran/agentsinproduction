#!/usr/bin/env bash
# Runs ON aip-ci-01. One attempt of experiment 05 (one agent vs a team) on one frozen task, then the validator.
#  1. opens a run on the gateway's admin port with the per-attempt cap (CAP_USD, the same for both configurations);
#  2. agent pod (ci-agent, Kata, gateway only): CONFIG A = one agent, CONFIG B = orchestrator + subagents + reviewer;
#     40 min hard deadline and 150 tool calls for the whole attempt in both; it produces a patch;
#  3. closes the run and reads what the gateway booked for it;
#  4. validator (cases/validate.py, criteria E2 + E10): path rules, stage 1 (commit tests x3), stage 2 (area suites once).
# Appends one JSON line to results/attempts-<round>.jsonl.   usage: attempt_team.sh <round-id> <T#> <A|B> <rep>
# Quote (QUOTE=1, round id quote-*): everything goes to quote/ instead of results/; quote attempts are never data of
# the experiment. VALIDATE=0 skips step 4 (the patch is kept; cases/validate.py can run on it later).
set -euo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
round="${1:?round}"; cid="${2:?task}"; cfg="${3:?config A or B}"; rep="${4:?rep}"; CAP="${CAP_USD:?per-attempt cap in USD}"; ADMIN="${ADMIN:-http://10.43.210.10:8081}"
CASES_DIR="${CASES_DIR:-/srv/ci/cases}"; GATEWAY_URL="${GATEWAY_URL:-http://10.43.210.10:8080}"   # overridden only by infra/test_attempt.py
case "$cfg" in A|B) ;; *) echo "config must be A or B" >&2; exit 1;; esac
[ -s "$CASES_DIR/$cid/meta.json" ] || { echo "task $cid has no meta.json" >&2; exit 1; }
if [ "${QUOTE:-0}" = 1 ]; then
  case "$round" in quote-*) ;; *) echo "quote rounds must be named quote-*"; exit 1;; esac
  base=quote
else
  case "$round" in quote-*) echo "a quote-* round needs QUOTE=1"; exit 1;; esac
  grep -q "^$cid," tasks.csv 2>/dev/null || { echo "task $cid is not in the frozen tasks.csv"; exit 1; }
  base=results
fi
run0="$(echo "$round-$cid-$cfg-r$rep" | tr 'A-Z' 'a-z')"; out="$base/attempts-$round.jsonl"; pd="$base/patches/$round"   # lower case: it names pods
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
  python3 - "$round" "$cid" "$rep" "$run" "$1" "${2:-}" "${3:-}" "$cfg" >> "$infra" <<'PY'
import json, os, sys, time
rnd, cid, rep, run, reason, fa, fg, cfg = sys.argv[1:]
grab = lambda f, tag: next((json.loads(l[len(tag):]) for l in reversed(open(f).readlines()) if l.startswith(tag)), {}) if f and os.path.exists(f) else {}
agent = grab(fa, "RESULT "); agent.pop("patch", None)
try: gw = json.loads(open(fg).read() or "{}") if fg and os.path.exists(fg) else {}
except ValueError: gw = {}
print(json.dumps({"round": rnd, "case": cid, "config": cfg, "rep": int(rep), "run": run, "reason": reason, "at": round(time.time()), "agent": agent,
                  "agent_pod": grab(fa, "POD "), "gateway": {"spent_usd": gw.get("spent_usd"), "calls": gw.get("calls"), "cap_usd": gw.get("cap_usd"),
                                                          "model_path_failures": gw.get("model_path_failures"),
                                                          "model_path_failure_reasons": gw.get("model_path_failure_reasons")}}))
PY
}
[ -s "$CASES_DIR/$cid/failure.txt" ] || { echo "task $cid has no failure.txt (written by team_host.py derive)"; exit 1; }
mkdir -p "$pd"
ADMIN_KEY_FILE="${ADMIN_KEY_FILE:-/srv/ci/admin-key}"
[ -s "$ADMIN_KEY_FILE" ] || { echo "missing gateway admin key: run infra/setup-lab.sh" >&2; exit 1; }
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat "$ADMIN_KEY_FILE")" | curl -sf --config - "$@"; }
# A halted gateway forwards nothing (a call above its reservation, an unwritten close, the provider refusing the
# account: no credit, key refused). Stop before a run id and an infrastructure try are used (added 2026-11-16, E20).
gw_halted=$(admin "$ADMIN/state" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("halted") or "")') || { echo "cannot read the gateway state; run $run not started" >&2; exit 1; }
[ -z "$gw_halted" ] || { echo "run $run not started: the gateway is halted ($gw_halted)" >&2; exit 1; }
opened=$(admin -X POST "$ADMIN/runs" -d "{\"run\": \"$run\", \"cap_usd\": $CAP}") || { echo "gateway refused to open run $run"; exit 1; }
# The run exists from here on. If the reply carries no usable token (an older gateway, an unexpected body), close it
# instead of leaving an open run behind.
run_token=$(printf '%s' "$opened" | python3 -c 'import json,sys; token=json.load(sys.stdin)["token"]; assert isinstance(token,str) and len(token)>=32; print(token)') || {
  admin -X POST "$ADMIN/runs/$run/close" -d '{}' >/dev/null || echo "could not close run $run either" >&2
  not_an_attempt "the gateway opened the run but returned no usable token"
  echo "gateway opened run $run but returned no usable token; the run was closed"; exit 1; }
unset opened
t0=$(date +%s)
RUN_TOKEN="$run_token" python3 cases/pod.py agent "$cid" "ag-$run" "${POD_DEADLINE:-2460}" --cpu "${AGENT_CPU:-4}" --memory "${AGENT_MEMORY:-10Gi}" \
  --env CONFIG="$cfg" --env RUN_ID="$run" --env GATEWAY_URL="$GATEWAY_URL" \
  --env MAX_TOOL_CALLS="${MAX_TOOL_CALLS:-150}" --env MAX_SECONDS="${MAX_SECONDS:-2340}" -- /opt/agent-venv/bin/python -u /code/agent.py > "/tmp/$run.agent" 2>&1 || true
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
# The provider refused the gateway's own account during this run (no credit: provider_billing; key refused:
# provider_auth). The gateway booked it to the run and halted. This is the gateway's word, not the pod's, and the pod
# cannot cause it; the agent did not get its model calls, whatever it reported and whatever is in its working copy.
# Not an attempt, whatever a validator would say about the partial patch: kept in the infra file and redone under a
# new run id (added 2026-11-16, criteria.md E20; in the collection of 16/11 such tries were journaled as attempts).
acct=$(python3 -c 'import json,sys
try: reasons = json.load(open(sys.argv[1])).get("model_path_failure_reasons") or {}
except Exception: reasons = {}
print(",".join(k for k in ("provider_billing", "provider_auth") if isinstance(reasons, dict) and reasons.get(k)))' "/tmp/$run.gw")
if [ -n "$acct" ]; then
  not_an_attempt "the provider refused the gateway's account during the run ($acct): the agent did not get its model calls" "/tmp/$run.agent" "/tmp/$run.gw"
  rm -f "$pd/$run.diff" "/tmp/$run".*
  echo "run $run: the provider refused the gateway's account ($acct); not recorded as an attempt (see $infra), the resume redoes it once the account is fixed and the gateway resumed" >&2
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
if [ "${VALIDATE:-1}" = 1 ]; then
  python3 cases/validate.py "$cid" "$pd/$run.diff" --prefix "va-$run" --parallel "${VALIDATE_PARALLEL:-1}" --save "$pd/$run.verdict.json" > "/tmp/$run.exec" 2>&1 || true
else
  echo 'VERDICT {"outcome": "not_run", "why": "VALIDATE=0: validate the saved patch later"}' > "/tmp/$run.exec"
fi
python3 - "$round" "$cid" "$rep" "$run" "$t0" "/tmp/$run.agent" "/tmp/$run.gw" "/tmp/$run.exec" "$unconfirmed" "$cfg" "$CAP" >> "$out" <<'PY'
import json, sys, time
rnd, cid, rep, run, t0, fa, fg, fe, unconfirmed, cfg, cap = sys.argv[1:]
grab = lambda f, tag: next((json.loads(l[len(tag):]) for l in reversed(open(f).readlines()) if l.startswith(tag)), {})
agent = grab(fa, "RESULT "); patch = agent.pop("patch", "") or ""; apod = grab(fa, "POD "); ex = grab(fe, "VERDICT ")
# the journal keeps the verdict and its counts; the per-sample detail stays in the saved verdict file
ex = {k: v for k, v in ex.items() if k != "samples"} | ({"n_samples": len(ex["samples"])} if isinstance(ex.get("samples"), list) else {})
agent["patch_bytes"] = len(patch.encode())
if unconfirmed == "1":      # the pod's "gateway_unavailable" had no confirmation outside the pod (see the top of this file)
    agent.update(outcome="error", claimed_outcome="gateway_unavailable",
                 error="reported gateway_unavailable, but the gateway booked no failed model call to this run; its own account: " + str(agent.get("error", ""))[:300])
gw = json.loads(open(fg).read() or "{}")
print(json.dumps({"round": rnd, "case": cid, "config": cfg, "rep": int(rep), "run": run, "cap_usd": float(cap), "agent": agent or {"outcome": "no_result"}, "agent_pod": apod,
                  "gateway": {"spent_usd": gw.get("spent_usd"), "calls": gw.get("calls"), "cap_usd": gw.get("cap_usd"),
                              "model_path_failures": gw.get("model_path_failures")},
                  "validator": ex, "wall_s": round(time.time() - int(t0), 1)}))
PY
rm -f "/tmp/$run".*
tail -1 "$out" | python3 -c 'import json,sys; r=json.load(sys.stdin); a=r["agent"]; print(r["run"], "agent:", a.get("outcome"), "tools", a.get("tool_calls"), "calls", a.get("model_calls"), "s", a.get("total_s"), "| gateway $", r["gateway"]["spent_usd"], "| validator:", r["validator"].get("outcome"), str(r["validator"].get("why", ""))[:80])'
[ "$close_ok" = 1 ] || { echo "the gateway did not confirm the close of run $run (recorded with unknown cost): make its state writable, close the run again, then resume the round" >&2; exit 1; }
