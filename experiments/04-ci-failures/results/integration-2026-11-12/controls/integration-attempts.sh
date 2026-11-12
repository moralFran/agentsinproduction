#!/usr/bin/env bash
# Integration check (2026-11-12), runs ON the VM in the FRESH run folder (never in the archive). NOT DATA: one real agent
# attempt per prompt version on gobwas/ws, to exercise the new gateway (run open/close with the admin token, ingress
# policy), the agent's result record, cases/validate.py and cases/check-round.py. Rounds are named v1-int and v2-int
# (attempt.sh picks prompt-v2.txt for round ids starting with v2, prompt-v1.txt otherwise).
# Model budget for this whole script: US$0.50. Per-attempt cap US$0.33; the second attempt's cap is lowered if the first
# one left less than that.   usage: integration-attempts.sh <run-dir> <out-dir>
set -uo pipefail
run_dir="$1"; out="$2"; mkdir -p "$out"; cd "$run_dir"; cid=gobwas-ws-a567dfd6; A=http://10.43.210.10:8081
[ -e ARCHIVE ] && { echo "refusing: archive folder"; exit 1; }
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat /srv/ci/admin-key)" | curl -s --max-time 8 --config - "$@"; }
spent() { admin "$A/state" | python3 -c 'import json,sys; print(json.load(sys.stdin)["spent_usd"])'; }
{
echo "== $(date -u +%FT%TZ) control: round runner with a WRONG admin key (no pod, no model call; pipefail must stop the round)"
echo wrong-key > "$out/wrong-admin-key"; ADMIN_KEY_FILE="$out/wrong-admin-key" cases/run-round.sh ctl-pipefail 3; echo "run-round.sh exit status: $?"
rm -f "$out/wrong-admin-key"; echo "journal exists: $([ -e results/attempts-ctl-pipefail.jsonl ] && echo yes || echo no); gateway spent: $(spent)"
echo "== $(date -u +%FT%TZ) attempt v1-int (prompt-v1.txt), cap 0.33"
cases/attempt.sh v1-int "$cid" 1; echo "attempt.sh exit status: $?"
s1=$(spent); cap2=$(python3 -c "print(min(0.33, round(0.50 - $s1, 2)))"); echo "gateway spent so far: $s1; cap for the second attempt: $cap2"
echo "== $(date -u +%FT%TZ) attempt v2-int (prompt-v2.txt), cap $cap2"
CAP_USD="$cap2" cases/attempt.sh v2-int "$cid" 1; echo "attempt.sh exit status: $?"
echo "== $(date -u +%FT%TZ) resume control: the same attempt again must be skipped (exit 0, no spend)"
before=$(spent); cases/attempt.sh v1-int "$cid" 1; echo "attempt.sh exit status: $?; spent before $before, after $(spent)"
echo "== $(date -u +%FT%TZ) cases/check-round.py on the two round journals (1 attempt each of 33: must report incomplete)"
for r in v1-int v2-int; do python3 cases/check-round.py "$r"; echo "check-round.py $r exit status: $?"; done
echo "== gateway records"
for r in v1-int v2-int; do run="$r-$(echo "$cid" | md5sum | cut -c1-8)-r1"; echo "$run: $(admin "$A/runs/$run")"; done
echo "state: $(admin "$A/state")"
echo "== $(date -u +%FT%TZ) done"
} > "$out/integration-attempts.log" 2>&1
KUBECONFIG=~/.kube/config kubectl -n ci-gateway logs deploy/gateway > "$out/gateway.log" 2>&1
cp results/attempts-v1-int.jsonl results/attempts-v2-int.jsonl "$out/" 2>/dev/null; mkdir -p "$out/patches"; cp -r results/patches/v1-int results/patches/v2-int "$out/patches/" 2>/dev/null
