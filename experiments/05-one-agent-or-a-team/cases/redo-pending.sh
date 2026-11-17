#!/usr/bin/env bash
# Runs ON aip-ci-01. Reproduces every prepared case (prep ok) that has no verdict in cases/repro.jsonl yet, e.g. after an
# infrastructure error of our own tooling (the protocol repeats an infrastructure error once).
set -uo pipefail
cd "$(dirname "$0")/.."
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
for cid in $(python3 - <<'PY'
import json, os
seen = {json.loads(l)["id"] for l in open("cases/repro.jsonl")} if os.path.exists("cases/repro.jsonl") else set()
for l in open("cases/prep-out/prep.jsonl"):
    try: d = json.loads(l)
    except Exception: continue
    if d.get("prep") == "ok" and d["id"] not in seen: print(d["id"])
PY
); do cases/repro.sh "$cid" 3 2>&1 | tail -1 | sed 's/^/[redo] /'; done
