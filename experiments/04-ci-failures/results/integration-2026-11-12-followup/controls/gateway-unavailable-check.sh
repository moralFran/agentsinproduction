#!/usr/bin/env bash
# Follow-up integration check (2026-11-12, harness d5e1195), runs ON the VM in the fresh run folder. NOT DATA and no
# model spend: the unmodified cases/attempt.sh is started for a smoke round, and its run is CLOSED from the host on the
# admin port as soon as the gateway shows it open, before the agent pod has started. The agent's first model call then
# meets a revoked token (403). Expected: agent outcome gateway_unavailable with an empty patch; one line in
# smoke/infra-<round>.jsonl; nothing in the journal; non-zero exit; the second invocation opens <run>-t2.
# usage: gateway-unavailable-check.sh <run-dir> <out-dir> <case-id>
set -uo pipefail
run_dir="$1"; out="$2"; cid="$3"; mkdir -p "$out"; cd "$run_dir"; export KUBECONFIG=~/.kube/config
A=http://10.43.210.10:8081; round=smoke-gwdown; run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r1"
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat /srv/ci/admin-key)" | curl -s --max-time 8 --config - "$@"; }
isopen() { admin "$A/runs/$1" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("open") is True else 1)' 2>/dev/null; }
{
python3 cases/smoke-failure.py "$cid"; echo "gateway state before: $(admin "$A/state")"
for run in "$run0" "$run0-t2"; do
  echo "== $(date -u +%FT%TZ) cases/attempt.sh $round $cid 1  (expected run id: $run)"
  ( SMOKE=1 cases/attempt.sh "$round" "$cid" 1; echo "attempt.sh exit status: $?" ) &
  n=0; until isopen "$run" || [ $n -ge 300 ]; do sleep 0.1; n=$((n + 1)); done
  echo "closed from the host after $n polls: $(admin -X POST "$A/runs/$run/close" -d '{}')"
  wait
  echo "journal smoke/attempts-$round.jsonl exists: $([ -e "smoke/attempts-$round.jsonl" ] && echo yes || echo no)"
  echo "lines in smoke/infra-$round.jsonl: $(wc -l < "smoke/infra-$round.jsonl" 2>/dev/null || echo 0)"
  echo "patch files left for the round: $(ls "smoke/patches/$round" 2>/dev/null | wc -l)"
  echo "admin view of $run: $(admin "$A/runs/$run")"
done
python3 - "smoke/infra-$round.jsonl" <<'PY'
import json, sys
for l in open(sys.argv[1]):
    r = json.loads(l); a = r.get("agent", {})
    print("infra record:", {"run": r["run"], "reason": r["reason"], "agent_outcome": a.get("outcome"), "agent_error": (a.get("error") or "")[:160], "model_calls": a.get("model_calls"),
                            "tool_calls": a.get("tool_calls"), "patch_key_present": "patch" in a, "agent_pod": r.get("agent_pod", {}).get("phase"), "gateway": r.get("gateway")})
PY
pod=$(kubectl -n ci-gateway get pods -l app=gateway -o jsonpath='{.items[0].metadata.name}')
echo "gateway log lines of these runs:"; kubectl -n ci-gateway logs "$pod" | grep -F -- "$run0" | cut -c1-230
echo "gateway state after: $(admin "$A/state")"
echo "== $(date -u +%FT%TZ) done"
} > "$out/gateway-unavailable-check.log" 2>&1
cp "smoke/infra-$round.jsonl" "$out/" 2>/dev/null
