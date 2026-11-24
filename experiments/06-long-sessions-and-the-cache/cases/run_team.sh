#!/usr/bin/env bash
# Runs ON aip-ctx-01. The collection of experiment 05 in the frozen order (order.csv, written by cases/order_team.py
# before any attempt): repetition by repetition. Inside a repetition the attempts START in the file's order, at most P
# at the same time; repetition r+1 starts only when every attempt of repetition r is in the journal (agent and validation).
# Each attempt is cases/attempt_team.sh with the same per-attempt cap (CAP_USD) for both configurations. Pods wait in
# the CPU/memory ledger of the lab (/srv/ci/queue.cpus, queue.mem), so P only bounds how many attempts are open.
# Resumable: an attempt already in the journal is skipped by attempt_team.sh.
#
# Budget rule (criteria.md E19, Francisco 16/11): repetition 1 starts only if 16 x CAP_USD fits in what is left of the
# gateway's total budget. Repetition r >= 2 starts only if what is left is at least MARGIN (1.25) x the cost of the most
# expensive complete repetition. The cost of a repetition is what the gateway booked between its start and its end
# (tries that never became an attempt included). Each decision is written to results/budget-<round>.jsonl. A repetition
# with attempts missing from the journal stops the round (exit 1): resume it before anything else.
#   usage: CAP_USD=<usd> run_team.sh <round-id> [P=4] [REPS=3]
set -euo pipefail
cd "$(dirname "$0")/.."; round="${1:?round id, e.g. c1}"; P="${2:-4}"; REPS="${3:-3}"; : "${CAP_USD:?per-attempt cap in USD}"
[ -s order.csv ] && [ -s tasks.csv ] || { echo "order.csv and tasks.csv must exist (frozen before the collection)" >&2; exit 1; }
want=$(head -1 order.csv | sed -n 's/.*tasks_sha256=\([0-9a-f]*\).*/\1/p'); have=$(sha256sum tasks.csv | cut -c1-16)
[ "$want" = "$have" ] || { echo "order.csv was generated from another tasks.csv ($want != $have)" >&2; exit 1; }
export CAP_USD VALIDATE_PARALLEL="${VALIDATE_PARALLEL:-4}"
ADMIN="${ADMIN:-http://10.43.210.10:8081}"; ADMIN_KEY_FILE="${ADMIN_KEY_FILE:-/srv/ci/admin-key}"; MARGIN="${MARGIN:-1.25}"
ATTEMPT="${ATTEMPT_SCRIPT:-cases/attempt_team.sh}"; mkdir -p results; budget="results/budget-$round.jsonl"
gw_state() {   # the gateway's totals; GW_STATE_CMD replaces the call in the local test
  if [ -n "${GW_STATE_CMD:-}" ]; then $GW_STATE_CMD; else printf 'header = "Authorization: Bearer %s"\n' "$(cat "$ADMIN_KEY_FILE")" | curl -sf --config - "$ADMIN/state"; fi
}
# gate.py <action> <rep>: "missing" prints how many attempts of the repetition are not in the journal; "decide" reads
# the gateway state on stdin and prints go / resume / stop <why>, writing a start record when it says go; "end" reads
# the state and writes the end record.
gate() { python3 cases/budget_gate.py "$1" "$2" "$round" "$CAP_USD" "$MARGIN"; }
done_reps=0
for rep in $(seq 1 "$REPS"); do
  if [ "$(gate missing "$rep")" = 0 ]; then   # complete in the journal; the end record is written here if a crash lost it
    state=$(gw_state) || { echo "cannot read the gateway state" >&2; exit 1; }
    printf '%s' "$state" | gate end "$rep"
    echo "== $round repetition $rep already complete"; done_reps=$rep; continue
  fi
  state=$(gw_state) || { echo "cannot read the gateway state" >&2; exit 1; }
  verdict=$(printf '%s' "$state" | gate decide "$rep")
  case "$verdict" in
    go|resume) ;;
    *) echo "== $round repetition $rep NOT started: $verdict"; break;;
  esac
  echo "== $round repetition $rep start $(date -u +%H:%M:%S) ($verdict)"
  awk -F, -v r="$rep" '!/^#/ && $2 == r { print $3, $4 }' order.csv |
    xargs -P "$P" -L 1 bash -c '"$2" "$0" "$3" "$4" "$1" 2>&1 | tail -1 || echo "attempt $3 $4 r$1: runner failed"' "$round" "$rep" "$ATTEMPT" || true
  left=$(gate missing "$rep")
  if [ "$left" != 0 ]; then
    echo "== $round repetition $rep INCOMPLETE: $left attempt(s) not in the journal; look at results/infra-$round.jsonl, then run the same command again" >&2
    halted=$(gw_state | python3 -c 'import json,sys; print(json.load(sys.stdin).get("halted") or "")' 2>/dev/null || true)   # E20: say why nothing more started
    [ -z "$halted" ] || echo "== the gateway is halted: $halted" >&2
    exit 1
  fi
  state=$(gw_state) || { echo "cannot read the gateway state" >&2; exit 1; }
  printf '%s' "$state" | gate end "$rep"
  echo "== $round repetition $rep done $(date -u +%H:%M:%S)"; done_reps=$rep
done
python3 - "$round" "$done_reps" <<'PY'
import csv, json, os, sys
rnd, reps = sys.argv[1], int(sys.argv[2])
want = {r["attempt"] for r in csv.DictReader(l for l in open("order.csv") if not l.startswith("#")) if int(r["rep"]) <= reps}
p = f"results/attempts-{rnd}.jsonl"
rows = [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
got = {f'{r["case"]}-{r["config"]}-r{r["rep"]}' for r in rows}
print(f"ROUND {rnd}: {reps} complete repetition(s); {len(got & want)} of {len(want)} attempts recorded; missing: {sorted(want - got) or 'none'}")
PY
