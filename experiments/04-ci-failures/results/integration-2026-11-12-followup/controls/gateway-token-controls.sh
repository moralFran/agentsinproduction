#!/usr/bin/env bash
# Follow-up integration control (2026-11-12), runs ON the VM host as the lab user. Admin port as in the first round, plus
# the per-run token of the follow-up gateway. No provider call is made: the token is exercised with a request whose
# max_tokens is not a number, which the gateway rejects with 400 AFTER the token check and BEFORE reserving or forwarding
# (403 = token refused; 400 "max_tokens is not a number" = token accepted). No token and no admin key is ever printed:
# reply bodies pass through a filter that replaces the token value, and the checks on files print counts only.
set -uo pipefail
A=http://10.43.210.10:8081; M=http://10.43.210.10:8080; K="${ADMIN_KEY_FILE:-/srv/ci/admin-key}"; B=$(mktemp); export KUBECONFIG=~/.kube/config
redact() { python3 -c 'import re,sys; print(re.sub(r"(\"token\": \")([^\"]+)(\")", lambda m: m.group(1) + "<redacted, %d characters>" % len(m.group(2)) + m.group(3), sys.stdin.read())[:260].replace("\n", " "))'; }
show() { printf '%-86s -> HTTP %s  %s\n' "$1" "$2" "$(redact < "$B")"; }
noauth() { local label="$1"; shift; show "$label" "$(curl -s -o "$B" -w '%{http_code}' --max-time 8 "$@")"; }
auth() { local label="$1"; shift; show "$label" "$(printf 'header = "Authorization: Bearer %s"\n' "$(cat "$K")" | curl -s -o "$B" -w '%{http_code}' --max-time 8 --config - "$@")"; }
tok() { local label="$1" token="$2"; shift 2; show "$label" "$(printf 'header = "x-run-token: %s"\n' "$token" | curl -s -o "$B" -w '%{http_code}' --max-time 8 --config - "$@")"; }
BAD='{"model": "claude-sonnet-5-5", "max_tokens": "not-a-number", "messages": [{"role": "user", "content": "x"}]}'
MSG=(-X POST "$M/v1/messages" -H 'content-type: application/json' -d "$BAD")
echo "== admin port (as in the first round)"
noauth "GET /state, no token"                                  "$A/state"
noauth "GET /state, wrong admin token"                         -H "Authorization: Bearer not-the-token" "$A/state"
noauth "POST /runs cap 0.01, no admin token"                   -X POST "$A/runs" -d '{"run": "fu-ctl-noauth", "cap_usd": 0.01}'
auth   "GET /state, admin token (positive control)"            "$A/state"
for cap in 0.34 1000 NaN Infinity 1e999 '"nan"' 0 -1; do auth "POST /runs cap $cap, admin token" -X POST "$A/runs" -d "{\"run\": \"fu-ctl-cap\", \"cap_usd\": $cap}"; done
auth   "POST /runs without cap, admin token"                   -X POST "$A/runs" -d '{"run": "fu-ctl-cap"}'
auth   "GET /runs/fu-ctl-cap (must not exist)"                 "$A/runs/fu-ctl-cap"
echo "== per-run token"
run="fu-ctl-token-$(date +%s)"
code=$(printf 'header = "Authorization: Bearer %s"\n' "$(cat "$K")" | curl -s -o "$B" -w '%{http_code}' --max-time 8 --config - -X POST "$A/runs" -d "{\"run\": \"$run\", \"cap_usd\": 0.33}")
show "POST /runs $run cap 0.33, admin token (opens; the reply carries the token once)" "$code"
TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("token", ""))' "$B"); echo "token returned: ${#TOKEN} characters (value not shown)"
auth   "GET /runs/$run, admin token (must carry no token and no token_hash)" "$A/runs/$run"
echo "keys in that reply: $(python3 -c 'import json,sys; print(sorted(json.load(open(sys.argv[1]))))' "$B")"
noauth "model port, no credential at all"                      "${MSG[@]}"
noauth "model port, only x-run-id of the OPEN run (the old scheme)" -H "x-run-id: $run" "${MSG[@]}"
tok    "model port, x-run-token = the run id (not the token)"  "$run" "${MSG[@]}"
tok    "model port, a wrong token of the right length"         "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" "${MSG[@]}"
tok    "model port, the run's token (accepted: 400 comes after the token check)" "$TOKEN" "${MSG[@]}"
auth   "POST /runs/$run again (reuse of the id must be refused)" -X POST "$A/runs" -d "{\"run\": \"$run\", \"cap_usd\": 0.33}"
auth   "POST /runs/$run/close, admin token"                    -X POST "$A/runs/$run/close" -d '{}'
tok    "model port, the same token AFTER close"                "$TOKEN" "${MSG[@]}"
auth   "GET /runs/$run after close"                            "$A/runs/$run"
echo "== where the token of that run can be found (exact string; counts only)"
pod=$(kubectl -n ci-gateway get pods -l app=gateway -o jsonpath='{.items[0].metadata.name}')
echo "gateway log, lines containing the token: $(kubectl -n ci-gateway logs "$pod" | grep -c -F -- "$TOKEN")"
echo "gateway state file, occurrences of the token: $(kubectl -n ci-gateway exec "$pod" -- cat /state/budget.json | grep -c -F -- "$TOKEN")"
echo "gateway state file, the token's sha256 present for this run: $(kubectl -n ci-gateway exec "$pod" -- cat /state/budget.json | grep -c -F -- "$(printf '%s' "$TOKEN" | sha256sum | cut -d' ' -f1)")"
echo "gateway log, lines for this run: $(kubectl -n ci-gateway logs "$pod" | grep -c -F -- "$run")"
kubectl -n ci-gateway logs "$pod" | grep -F -- "$run" | cut -c1-240
echo "gateway log, any key named token: $(kubectl -n ci-gateway logs "$pod" | grep -c '"token')"
unset TOKEN
noauth "host -> model port GET /healthz"                       "$M/healthz"
auth   "GET /state, admin token (after the controls: nothing spent by them)" "$A/state"
rm -f "$B"
