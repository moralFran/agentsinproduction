#!/usr/bin/env bash
# Follow-up integration check (2026-11-12), runs ON the VM in the fresh run folder. NOT DATA: one live agent attempt per
# smoke case (SMOKE=1, round smoke-fu, prompt-v1) through the token gateway. Budget of this script: US$0.50; cap 0.33 per
# attempt, the second lowered if the first left less. While the second attempt is open, the old scheme is tried against
# it from the host (only x-run-id of the open run: must be 403). Afterwards the files of each attempt are searched for
# the run's token WITHOUT knowing it: every 43-character URL-safe string found is hashed and compared with the
# token_hash the gateway keeps for that run. Counts only; nothing secret is printed.
# usage: smoke-attempts.sh <run-dir> <out-dir> <case-id> <case-id>
set -uo pipefail
run_dir="$1"; out="$2"; first="$3"; second="$4"; mkdir -p "$out"; cd "$run_dir"; export KUBECONFIG=~/.kube/config
A=http://10.43.210.10:8081; M=http://10.43.210.10:8080; round=smoke-fu
[ -e ARCHIVE ] && { echo "refusing: archive folder"; exit 1; }
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat /srv/ci/admin-key)" | curl -s --max-time 8 --config - "$@"; }
spent() { admin "$A/state" | python3 -c 'import json,sys; print(json.load(sys.stdin)["spent_usd"])'; }
runid() { echo "$round-$(echo "$1" | md5sum | cut -c1-8)-r1"; }
{
echo "== $(date -u +%FT%TZ) failure text for the smoke cases"; python3 cases/smoke-failure.py "$first" "$second"
base=$(spent); echo "gateway spent before this script: $base"
echo "== $(date -u +%FT%TZ) attempt on $first, cap 0.33"
SMOKE=1 cases/attempt.sh "$round" "$first" 1; echo "attempt.sh exit status: $?"
cap2=$(python3 -c "print(min(0.33, round(0.50 - ($(spent) - $base), 2)))"); echo "spent by this script so far: $(python3 -c "print(round($(spent) - $base, 6))"); cap for the second attempt: $cap2"
echo "== $(date -u +%FT%TZ) attempt on $second, cap $cap2"
( sleep 60; r=$(runid "$second"); echo "while $r is open: admin view open=$(admin "$A/runs/$r" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("open"))'); model port with only x-run-id -> HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -X POST "$M/v1/messages" -H 'content-type: application/json' -H "x-run-id: $r" -d '{"model": "claude-sonnet-5-5", "max_tokens": "not-a-number", "messages": [{"role": "user", "content": "x"}]}')" ) &
SMOKE=1 CAP_USD="$cap2" cases/attempt.sh "$round" "$second" 1; echo "attempt.sh exit status: $?"; wait
echo "== $(date -u +%FT%TZ) gateway records (admin GET; must carry no token)"
for c in "$first" "$second"; do r=$(runid "$c"); echo "$r: $(admin "$A/runs/$r")"; done
echo "state: $(admin "$A/state")"; echo "spent by this script: $(python3 -c "print(round($(spent) - $base, 6))")"
echo "== search for each run's token by its hash"
pod=$(kubectl -n ci-gateway get pods -l app=gateway -o jsonpath='{.items[0].metadata.name}')
kubectl -n ci-gateway logs "$pod" > "$out/gateway.log"; kubectl -n ci-gateway exec "$pod" -- cat /state/budget.json > "$out/.state.json"
for c in "$first" "$second"; do r=$(runid "$c"); admin "$A/runs/$r" > "$out/.admin-$r.json"
python3 - "$out/.state.json" "$r" "$out/gateway.log" "$out/.admin-$r.json" "smoke/attempts-$round.jsonl" "smoke/patches/$round/$r.diff" "/srv/ci/logs/ag-$r.log" <<'PY'
import hashlib, json, re, sys
state = json.load(open(sys.argv[1])); run = sys.argv[2]; want = state["runs"][run].get("token_hash")
print(f"{run}: gateway state keeps token_hash: {bool(want)} ({len(want or '')} hex characters); a field named token in the state file: {'token' in state['runs'][run]}")
for path in sys.argv[3:]:
    try: text = open(path, errors="replace").read()
    except OSError as e: print(f"  {path}: not read ({e.strerror})"); continue
    candidates = set(re.findall(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])", text))
    hits = sum(hashlib.sha256(c.encode()).hexdigest() == want for c in candidates)
    print(f"  {path.split('/')[-1]}: {len(text)} bytes, {len(candidates)} candidate strings, matching the token: {hits}, mentions of RUN_TOKEN: {text.count('RUN_TOKEN')}, of x-run-token: {text.count('x-run-token')}")
PY
done
rm -f "$out"/.state.json "$out"/.admin-*.json
echo "leftover /tmp files of the attempts: $(ls /tmp | grep -c "^$round-")"
echo "== $(date -u +%FT%TZ) done"
} > "$out/smoke-attempts.log" 2>&1
cp "smoke/attempts-$round.jsonl" "$out/" 2>/dev/null; mkdir -p "$out/patches"; cp -r "smoke/patches/$round" "$out/patches/" 2>/dev/null
