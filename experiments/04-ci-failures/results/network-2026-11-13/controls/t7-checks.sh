#!/usr/bin/env bash
# T7 (2026-11-13), runs ON the VM in the fresh run folder after the four changed files were copied in and the lab was
# redeployed with the DUMMY key. Live check of the uncommitted change "the gateway confirms a gateway_unavailable claim
# at close". NOT DATA; no model call may be forwarded (proved at the end from the gateway log).
# Pods are built WITHOUT the network gate of this round (NETGATE=0): the change under test is the gateway one.
# usage: t7-checks.sh <run-dir> <out-dir> <case-id> [A B C D]
set -uo pipefail
run_dir="$1"; out="$2"; cid="$3"; shift 3; checks="${*:-A B C D}"; mkdir -p "$out"; cd "$run_dir"; export KUBECONFIG=~/.kube/config NETGATE=0
A=http://10.43.210.10:8081
admin() { printf 'header = "Authorization: Bearer %s"\n' "$(cat /srv/ci/admin-key)" | curl -s --max-time 8 --config - "$@"; }
isopen() { admin "$A/runs/$1" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("open") is True else 1)' 2>/dev/null; }
gwlog() { kubectl -n ci-gateway logs "$(kubectl -n ci-gateway get pods -l app=gateway -o jsonpath='{.items[0].metadata.name}')"; }
python3 cases/smoke-failure.py "$cid" > "$out/smoke-failure.txt" 2>&1
for check in $checks; do case "$check" in
A) { round=smoke-gwconf; run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r1"
  echo "gateway state before: $(admin "$A/state")"
  for run in "$run0" "$run0-t2"; do
    echo "== $(date -u +%FT%TZ) SMOKE=1 cases/attempt.sh $round $cid 1  (expected run id: $run)"
    ( SMOKE=1 cases/attempt.sh "$round" "$cid" 1; echo "attempt.sh exit status: $?" ) &
    n=0; until isopen "$run" || [ $n -ge 300 ]; do sleep 0.1; n=$((n + 1)); done
    echo "closed from the host after $n polls; close reply: $(admin -X POST "$A/runs/$run/close" -d '{}')"
    wait
    echo "journal smoke/attempts-$round.jsonl exists: $([ -e "smoke/attempts-$round.jsonl" ] && echo yes || echo no)"
    echo "lines in smoke/infra-$round.jsonl: $(wc -l < "smoke/infra-$round.jsonl" 2>/dev/null || echo 0)"
    echo "admin view of $run after attempt.sh: $(admin "$A/runs/$run")"
    echo "a later close of $run replies: $(admin -X POST "$A/runs/$run/close" -d '{}')"
  done
  echo "infra file:"; cat "smoke/infra-$round.jsonl"
  echo "gateway log lines of these runs:"; gwlog | grep -F -- "$run0" | cut -c1-260
  echo "== $(date -u +%FT%TZ) done"; } > "$out/A-confirmed-claim.log" 2>&1
  cp "smoke/infra-$round.jsonl" "$out/A-infra-$round.jsonl" 2>/dev/null ;;
B) { round=smoke-gwunconf; run0="$round-$(echo "$cid" | md5sum | cut -c1-8)-r1"
  sed 's#GATEWAY_URL=http://10.43.210.10:8080#GATEWAY_URL=http://10.43.210.10:8081#' cases/attempt.sh > cases/attempt-b.sh; chmod +x cases/attempt-b.sh
  echo "VM-only copy cases/attempt-b.sh; the only difference from cases/attempt.sh:"; diff cases/attempt.sh cases/attempt-b.sh
  echo "== $(date -u +%FT%TZ) SMOKE=1 cases/attempt-b.sh $round $cid 1  (run id $run0; the pod is told the gateway is on port 8081, which the policy does not allow)"
  ( sleep 20; echo "while the pod runs: admin view of $run0: $(admin "$A/runs/$run0")" ) &
  t0=$(date +%s); SMOKE=1 cases/attempt-b.sh "$round" "$cid" 1; echo "attempt-b.sh exit status: $? after $(( $(date +%s) - t0 )) s"; wait
  echo "journal rows:"; cat "smoke/attempts-$round.jsonl" 2>/dev/null
  echo "lines in smoke/infra-$round.jsonl: $(wc -l < "smoke/infra-$round.jsonl" 2>/dev/null || echo 0)"
  echo "stored patch: $(wc -c < "smoke/patches/$round/$run0.diff" 2>/dev/null) bytes"
  echo "admin view of $run0 afterwards: $(admin "$A/runs/$run0")"
  echo "a later close replies: $(admin -X POST "$A/runs/$run0/close" -d '{}')"
  echo "== $(date -u +%FT%TZ) same case and repetition again"
  SMOKE=1 cases/attempt-b.sh "$round" "$cid" 1; echo "attempt-b.sh exit status: $?"
  echo "agent pod log (/srv/ci/logs/ag-$run0.log), last lines:"; tail -5 "/srv/ci/logs/ag-$run0.log" 2>/dev/null | cut -c1-600
  echo "gateway log lines of this run:"; gwlog | grep -F -- "$run0" | cut -c1-260
  echo "== $(date -u +%FT%TZ) done"; } > "$out/B-unconfirmed-claim.log" 2>&1
  cp "smoke/attempts-$round.jsonl" "$out/B-attempts-$round.jsonl" 2>/dev/null ;;
C) { echo "== $(date -u +%FT%TZ) REPRO_OUT=$out/C-repro.jsonl cases/repro.sh $cid 3 (executor.py sha256 $(sha256sum executor/executor.py | cut -c1-16))"
  rm -f "$out/C-repro.jsonl"; REPRO_OUT="$out/C-repro.jsonl" cases/repro.sh "$cid" 3; echo "repro.sh exit status: $?"
  python3 - "$out/C-repro.jsonl" <<'PY'
import json, sys
r = json.loads(open(sys.argv[1]).readlines()[-1]); ic = r.get("integrity_control", {})
print("verdict:", r.get("verdict"), "| integrity_control outcome:", ic.get("outcome"), "| suite samples:", [s.get("outcome") for s in ic.get("suite", [])], "| hidden samples:", [s.get("outcome") for s in ic.get("hidden", [])])
print("cache_control:", {k: v for k, v in (r.get("cache_control") or {}).items() if k != "runs"})
PY
  for p in rb rf rh rc; do f="/srv/ci/logs/$p-$cid.log"; echo "$f: $(grep -c -i -e 'git status failed' -e 'dubious ownership' "$f" 2>/dev/null) lines with 'git status failed' or 'dubious ownership'"; done
  echo "== $(date -u +%FT%TZ) done"; } > "$out/C-safe-directory.log" 2>&1 ;;
D) { echo "== $(date -u +%FT%TZ) agent pod built by cases/pod.py (harness spec), command replaced by the two shell forms"
  RUN_TOKEN=dummy-not-a-token python3 cases/pod.py agent "$cid" t7d-shell 180 -- bash -c '
echo "--- PATH given to the container: $PATH"
echo "--- new form: bash -o pipefail -c"; bash -o pipefail -c "command -v go python3 git; go version; echo PATH=\$PATH"; echo "exit status $?"
echo "--- old form: bash -lc"; bash -lc "command -v go python3 git; go version; echo PATH=\$PATH"; echo "exit status $?"
echo "--- which file sets PATH for a login shell (uid $(id -u), HOME=$HOME)"; grep -n "PATH" /etc/profile /etc/profile.d/* /etc/bash.bashrc "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.bash_login" 2>&1 | cut -c1-200
echo "--- bash -lxc trace of the PATH assignment"; bash -lxc true 2>&1 | grep -n -e "PATH" -e "id -u" | head -8
echo "--- /etc/profile, first lines"; sed -n 1,12p /etc/profile'
  echo "pod log:"; cat /srv/ci/logs/t7d-shell.log
  echo "== $(date -u +%FT%TZ) done"; } > "$out/D-shell-path.log" 2>&1 ;;
esac; done
gwlog > "$out/gateway.log" 2>&1
echo "lines with \"verdict\": \"forwarded\" in the gateway log: $(grep -c '"verdict": "forwarded"' "$out/gateway.log")" > "$out/no-forwarded-call.txt"
echo "distinct verdicts in the gateway log: $(grep -o '"verdict": "[^"]*"' "$out/gateway.log" | sort | uniq -c | tr '\n' ';')" >> "$out/no-forwarded-call.txt"
echo "gateway state at the end: $(admin "$A/state")" >> "$out/no-forwarded-call.txt"
