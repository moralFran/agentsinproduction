#!/usr/bin/env bash
# Review follow-up (2026-11-13, second session), runs ON the VM in the fresh run folder after cases/attempt.sh,
# cases/validate.py and gateway/gateway.py of the working tree were copied in and the lab redeployed with the DUMMY key.
# NOT DATA; no model call may be forwarded (checked at the end from the gateway log). usage: b-checks.sh <run-dir> <out-dir> <case-id>
set -uo pipefail
run_dir="$1"; out="$2"; cid="$3"; mkdir -p "$out"; cd "$run_dir"; export KUBECONFIG=~/.kube/config
A=http://10.43.210.10:8081; M=http://10.43.210.10:8080
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat /srv/ci/admin-key)" | curl -s --max-time 8 --config - "$@"; }
isopen() { admin "$A/runs/$1" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("open") is True else 1)' 2>/dev/null; }
gwlog() { kubectl -n ci-gateway logs "$(kubectl -n ci-gateway get pods -l app=gateway -o jsonpath='{.items[0].metadata.name}')"; }
python3 cases/smoke-failure.py "$cid" > "$out/smoke-failure.txt" 2>&1
{ round=smoke-gatefail; run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r1"
  echo "B1. The gate is made to fail for the agent pod: NETGATE_PUBLIC=10.43.210.10:8080 (the gateway's model port, which the"
  echo "    agent's policy allows, so that canary is never refused) and NETGATE_DEADLINE=8. No model call is possible: the main container never starts."
  echo "gateway state before: $(admin "$A/state")"
  for run in "$run0" "$run0-t2"; do
    echo "== $(date -u +%FT%TZ) NETGATE_PUBLIC=10.43.210.10:8080 NETGATE_DEADLINE=8 SMOKE=1 cases/attempt.sh $round $cid 1  (expected run id: $run)"
    NETGATE_PUBLIC=10.43.210.10:8080 NETGATE_DEADLINE=8 SMOKE=1 cases/attempt.sh "$round" "$cid" 1; echo "attempt.sh exit status: $?"
    echo "journal smoke/attempts-$round.jsonl exists: $([ -e "smoke/attempts-$round.jsonl" ] && echo yes || echo no)"
    echo "lines in smoke/infra-$round.jsonl: $(wc -l < "smoke/infra-$round.jsonl" 2>/dev/null || echo 0)"
    echo "admin view of $run: $(admin "$A/runs/$run")"
  done
  echo "infra file:"; cat "smoke/infra-$round.jsonl"
  echo "gateway log lines of these runs:"; gwlog | grep -F -- "$run0" | cut -c1-300
  echo "== $(date -u +%FT%TZ) done"; } > "$out/B1-gate-failure.log" 2>&1
cp "smoke/infra-smoke-gatefail.jsonl" "$out/B1-infra-smoke-gatefail.jsonl" 2>/dev/null
{ round=smoke-gwconf2; run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r1"
  echo "B2. Run closed from the host before the pod's first model call (as check A of the first session). Pods built with NETGATE=0."
  for run in "$run0"; do
    echo "== $(date -u +%FT%TZ) NETGATE=0 SMOKE=1 cases/attempt.sh $round $cid 1  (expected run id: $run)"
    ( NETGATE=0 SMOKE=1 cases/attempt.sh "$round" "$cid" 1; echo "attempt.sh exit status: $?" ) &
    n=0; until isopen "$run" || [ $n -ge 300 ]; do sleep 0.1; n=$((n + 1)); done
    echo "closed from the host after $n polls; close reply: $(admin -X POST "$A/runs/$run/close" -d '{}')"
    wait
    echo "journal smoke/attempts-$round.jsonl exists: $([ -e "smoke/attempts-$round.jsonl" ] && echo yes || echo no)"
    echo "lines in smoke/infra-$round.jsonl: $(wc -l < "smoke/infra-$round.jsonl" 2>/dev/null || echo 0)"
    echo "admin view of $run after attempt.sh: $(admin "$A/runs/$run")"
    echo "a later close of $run replies: $(admin -X POST "$A/runs/$run/close" -d '{}')"
  done
  echo "infra file:"; cat "smoke/infra-$round.jsonl"
  echo "gateway log lines of this run:"; gwlog | grep -F -- "$run0" | cut -c1-300
  echo "== $(date -u +%FT%TZ) done"; } > "$out/B2-run-closed.log" 2>&1
cp "smoke/infra-smoke-gwconf2.jsonl" "$out/B2-infra-smoke-gwconf2.jsonl" 2>/dev/null
{ run="smoke-b3-$(date +%s)"
  echo "B3. From the VM host: a run is opened, two requests with its VALID token are sent that the gateway refuses for their format"
  echo "    (a field that is not allowed; a model that is not allowed), the run is closed. Neither may count as a model-path failure."
  echo "== $(date -u +%FT%TZ) open $run"
  opened=$(admin -X POST "$A/runs" -d "{\"run\": \"$run\", \"cap_usd\": 0.01}")
  echo "open reply (token removed): $(printf '%s' "$opened" | python3 -c 'import json,sys; d=json.load(sys.stdin); d["token"]="<%d characters>" % len(d.get("token","")); print(json.dumps(d))')"
  printf '%s' "$opened" | python3 -c 'import json,sys; print("header = \"x-run-token: %s\"" % json.load(sys.stdin)["token"])' > "/tmp/$run.hdr"; chmod 600 "/tmp/$run.hdr"; unset opened
  post() { curl -s --max-time 8 --config "/tmp/$run.hdr" -o "/tmp/$run.body" -w '%{http_code}' -X POST "$M/v1/messages" -H 'content-type: application/json' -d "$1"; echo " $(head -c 200 "/tmp/$run.body")"; }
  echo "request 1 (allowed model, fields \"stream\": true and an unknown one): HTTP $(post '{"model": "claude-sonnet-5-5", "max_tokens": 1, "stream": true, "aip_field_not_allowed": 1, "messages": [{"role": "user", "content": "x"}]}')"
  echo "request 2 (model not in the price list): HTTP $(post '{"model": "not-an-allowed-model", "max_tokens": 1, "messages": [{"role": "user", "content": "x"}]}')"
  echo "admin view while open: $(admin "$A/runs/$run")"
  echo "close reply: $(admin -X POST "$A/runs/$run/close" -d '{}')"
  echo "control, same token after the close (this one IS a model-path failure, reason run_closed): HTTP $(post '{"model": "claude-sonnet-5-5", "max_tokens": 1, "messages": [{"role": "user", "content": "x"}]}')"
  echo "admin view after the control: $(admin "$A/runs/$run")"
  rm -f "/tmp/$run.hdr" "/tmp/$run.body"
  echo "gateway log lines of this run and of the refused requests:"; gwlog | grep -e "$run" -e '"verdict": "refused"' | tail -8 | cut -c1-300
  echo "== $(date -u +%FT%TZ) done"; } > "$out/B3-valid-token-forbidden-request.log" 2>&1
gwlog > "$out/gateway.log" 2>&1
{ echo "lines with \"verdict\": \"forwarded\" in the gateway log: $(grep -c '"verdict": "forwarded"' "$out/gateway.log")"
  echo "verdicts in the gateway log: $(grep -o '"verdict": "[^"]*"' "$out/gateway.log" | sort | uniq -c | tr '\n' ';')"
  echo "gateway state at the end: $(admin "$A/state")"; } > "$out/no-forwarded-call.txt"
echo "$(date -u +%FT%TZ) B_DONE" >> "$out/no-forwarded-call.txt"
