#!/usr/bin/env bash
# Integration control (2026-11-12), runs ON the VM host as the lab user (the round runner's position). Admin port of the
# gateway with and without the token; invalid caps; one run opened and closed (no model call, nothing spent).
# The token is read from /srv/ci/admin-key and sent through curl's stdin configuration; it is never printed.
set -uo pipefail
A=http://10.43.210.10:8081; M=http://10.43.210.10:8080; K="${ADMIN_KEY_FILE:-/srv/ci/admin-key}"; B=$(mktemp)
show() { printf '%-78s -> HTTP %s  %s\n' "$1" "$2" "$(head -c 200 "$B" | tr -d '\n')"; }
noauth() { local label="$1"; shift; show "$label" "$(curl -s -o "$B" -w '%{http_code}' --max-time 8 "$@")"; }
auth() { local label="$1"; shift; show "$label" "$(printf 'header = "Authorization: Bearer %s"\n' "$(cat "$K")" | curl -s -o "$B" -w '%{http_code}' --max-time 8 --config - "$@")"; }
echo "admin key file: mode $(stat -c %a "$K"), $(wc -c < "$K") bytes (content not shown)"
noauth "GET /state, no token"                                  "$A/state"
noauth "GET /state, wrong token"                               -H "Authorization: Bearer not-the-token" "$A/state"
noauth "POST /runs cap 0.01, no token"                         -X POST "$A/runs" -d '{"run": "int-ctl-noauth", "cap_usd": 0.01}'
auth   "GET /state, with token (positive control)"             "$A/state"
auth   "POST /runs cap 0.34 (above MAX_RUN_USD 0.33), token"   -X POST "$A/runs" -d '{"run": "int-ctl-cap-034", "cap_usd": 0.34}'
auth   "POST /runs cap 1000, token"                            -X POST "$A/runs" -d '{"run": "int-ctl-cap-1000", "cap_usd": 1000}'
auth   "POST /runs cap NaN, token"                             -X POST "$A/runs" -d '{"run": "int-ctl-cap-nan", "cap_usd": NaN}'
auth   "POST /runs cap Infinity, token"                        -X POST "$A/runs" -d '{"run": "int-ctl-cap-inf", "cap_usd": Infinity}'
auth   "POST /runs cap 1e999, token"                           -X POST "$A/runs" -d '{"run": "int-ctl-cap-1e999", "cap_usd": 1e999}'
auth   "POST /runs cap \"nan\" (string), token"                -X POST "$A/runs" -d '{"run": "int-ctl-cap-str", "cap_usd": "nan"}'
auth   "POST /runs cap 0, token"                               -X POST "$A/runs" -d '{"run": "int-ctl-cap-0", "cap_usd": 0}'
auth   "POST /runs cap -1, token"                              -X POST "$A/runs" -d '{"run": "int-ctl-cap-neg", "cap_usd": -1}'
auth   "POST /runs without cap, token"                         -X POST "$A/runs" -d '{"run": "int-ctl-cap-missing"}'
auth   "POST /runs cap 0.33, token (positive control: opens)"  -X POST "$A/runs" -d '{"run": "int-ctl-open", "cap_usd": 0.33}'
noauth "GET /runs/int-ctl-open, no token"                      "$A/runs/int-ctl-open"
auth   "GET /runs/int-ctl-open, token"                         "$A/runs/int-ctl-open"
noauth "POST /runs/int-ctl-open/close, no token"               -X POST "$A/runs/int-ctl-open/close" -d '{}'
auth   "POST /runs/int-ctl-open/close, token"                  -X POST "$A/runs/int-ctl-open/close" -d '{}'
for r in int-ctl-noauth int-ctl-cap-034 int-ctl-cap-1000 int-ctl-cap-nan int-ctl-cap-inf int-ctl-cap-1e999 int-ctl-cap-str int-ctl-cap-0 int-ctl-cap-neg int-ctl-cap-missing; do
  auth "GET /runs/$r, token (must not exist)" "$A/runs/$r"; done
noauth "host -> model port GET /healthz (node traffic is exempt from NetworkPolicy)" "$M/healthz"
noauth "host -> model port POST /v1/messages, closed run id (no provider call)" -X POST "$M/v1/messages" -H 'content-type: application/json' -H 'x-run-id: int-ctl-open' -d '{"model": "claude-sonnet-5-5", "max_tokens": 1, "messages": [{"role": "user", "content": "x"}]}'
auth   "GET /state, with token (after the controls)"           "$A/state"
rm -f "$B"
