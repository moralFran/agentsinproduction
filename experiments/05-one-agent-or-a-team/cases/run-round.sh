#!/usr/bin/env bash
# Runs ON aip-ci-01. One version of the agent over the frozen cases, in protocol order: repetition 1 across every case
# of cases.csv (in file order), then repetition 2, then 3. At most P attempts at the same time (default 3); a repetition
# starts only when the previous one has finished. Each attempt: cases/attempt.sh (per-attempt cap US$0.33 in the gateway,
# executor validation). The gateway's total budget stops the version at its cap.   usage: run-round.sh <round-id> [P]
set -euo pipefail
cd "$(dirname "$0")/.."; round="${1:?round id, e.g. v1}"; P="${2:-3}"
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
ids=$(python3 -c 'import csv; [print(r["case_id"]) for r in csv.DictReader(open("cases/cases.csv"))]')
for rep in 1 2 3; do
  echo "== $round repetition $rep start $(date -u +%H:%M:%S)"
  printf '%s\n' $ids | xargs -P "$P" -I{} bash -o pipefail -c 'cases/attempt.sh "$0" {} "$1" 2>&1 | tail -1' "$round" "$rep"
  echo "== $round repetition $rep done $(date -u +%H:%M:%S)"
done
python3 cases/check-round.py "$round"
