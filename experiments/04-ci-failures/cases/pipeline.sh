#!/usr/bin/env bash
# Runs ON aip-ci-01. Worker: takes candidates from mining/candidates-*.jsonl in order (Go and Python interleaved),
# skips those already claimed, prepares each (box image, WITH network, as the VM user) and reproduces it (executor pods,
# no network). Stops when cases/repro.jsonl holds 30 "reproduced" verdicts. Several workers may run: a lock file per
# candidate keeps them apart.   usage: pipeline.sh <worker-id> [max-candidates]
set -uo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
docker info >/dev/null 2>&1 || { echo "docker does not answer without sudo: run infra/install-docker.sh and log in again" >&2; exit 1; }   # check added 2026-11-12
w="${1:-1}"; max="${2:-1000}"; done_n=0; mkdir -p cases/locks cases/prep-out
while [ "$done_n" -lt "$max" ]; do
  n=$(grep -c '"verdict": "reproduced"' cases/repro.jsonl 2>/dev/null); n=${n:-0}
  [ "$n" -ge 30 ] && { echo "[$w] 30 reproduced; stopping"; exit 0; }
  line=$(python3 cases/claim.py)
  [ -z "$line" ] && { echo "[$w] no unclaimed candidate; waiting"; sleep 60; continue; }
  done_n=$((done_n + 1))
  out=$(docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -v /srv/ci:/srv/ci -v "$PWD":/lab aip-ci-box:1 \
        timeout 2400 python3 /lab/cases/prep.py "$line" 2>&1 | grep -E '^\{|PREP_FAIL' | tail -1)
  [ -n "$out" ] || out=$(echo "$line" | python3 -c 'import json,re,sys; c=json.load(sys.stdin); print(json.dumps({"id": re.sub(r"[^a-z0-9]+","-",c["repo"].lower()).strip("-")[:40]+"-"+c["broken_sha"][:8], "prep": "fail", "why": "no output (timeout or crash)"}))')
  echo "$out" >> cases/prep-out/prep.jsonl
  cid=$(echo "$out" | python3 -c 'import json,sys
try: d=json.loads(sys.stdin.read()); print(d["id"] if d.get("prep")=="ok" else "")
except Exception: print("")')
  if [ -z "$cid" ]; then echo "[$w] prep failed: ${out:0:220}"; continue; fi
  cases/repro.sh "$cid" 3 2>&1 | tail -1 | sed "s/^/[$w] /"
done
