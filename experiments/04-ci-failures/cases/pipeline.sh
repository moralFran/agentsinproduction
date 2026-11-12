#!/usr/bin/env bash
# Runs ON aip-ci-01. Worker: takes candidates from mining/candidates-*.jsonl in order (Go and Python interleaved),
# skips those already claimed, prepares each (per-case Kata pods with dependency-download egress) and reproduces it (executor pods,
# no network). Processes every available candidate; exits when no unclaimed candidate remains. A lock file per
# candidate keeps them apart.   usage: pipeline.sh <worker-id> [max-candidates]
set -uo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
kubectl get namespace ci-prep >/dev/null || { echo "run infra/setup-lab.sh before preparing cases" >&2; exit 1; }
w="${1:-1}"; max="${2:-1000}"; done_n=0; mkdir -p cases/locks cases/prep-out
while [ "$done_n" -lt "$max" ]; do
  line=$(python3 cases/claim.py) || exit 1
  [ -z "$line" ] && { echo "[$w] no unclaimed candidate; done"; exit 0; }
  done_n=$((done_n + 1))
  out=$(python3 cases/prep.py "$line" 2>&1 | grep -E '^\{|PREP_FAIL' | tail -1)
  [ -n "$out" ] || out=$(echo "$line" | python3 -c 'import json,re,sys; c=json.load(sys.stdin); print(json.dumps({"id": re.sub(r"[^a-z0-9]+","-",c["repo"].lower()).strip("-")[:40]+"-"+c["broken_sha"][:8], "prep": "fail", "why": "no output (timeout or crash)"}))')
  echo "$out" >> cases/prep-out/prep.jsonl
  cid=$(echo "$out" | python3 -c 'import json,sys
try: d=json.loads(sys.stdin.read()); print(d["id"] if d.get("prep")=="ok" else "")
except Exception: print("")')
  if [ -z "$cid" ]; then echo "[$w] prep failed: ${out:0:220}"; continue; fi
  cases/repro.sh "$cid" 3 2>&1 | tail -1 | sed "s/^/[$w] /"
done
