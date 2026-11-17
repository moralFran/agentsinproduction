#!/usr/bin/env bash
# Runs ON aip-ci-01, after every candidate is settled. The protocol repeats an infrastructure error once: every case whose
# verdict is infra_error (its executor pod hit the 40-minute deadline while 4 workers shared the 8 CPUs) is reproduced
# again, one at a time, with the machine otherwise idle. The first verdict is kept in cases/repro-infra-first.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
ids=$(python3 -c 'import json; [print(json.loads(l)["id"]) for l in open("cases/repro.jsonl") if json.loads(l)["verdict"] == "infra_error"]')
for cid in $ids; do
  grep "\"id\": \"$cid\"" cases/repro.jsonl >> cases/repro-infra-first.jsonl
  python3 - "$cid" <<'PY'
import sys
rows = open("cases/repro.jsonl").read().splitlines()
open("cases/repro.jsonl.tmp", "w").write("".join(l + "\n" for l in rows if f'"id": "{sys.argv[1]}"' not in l))
import os; os.replace("cases/repro.jsonl.tmp", "cases/repro.jsonl")
PY
  cases/repro.sh "$cid" 3 2>&1 | tail -1 | sed 's/^/[retry] /'
done
