#!/usr/bin/env bash
# Runs ON aip-ci-01. Forgets one candidate so a worker prepares it again (after a fix to the tooling).
set -euo pipefail; cd "$(dirname "$0")/.."
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
cid="${1:?case id}"; key="${2:?lock key repo__name__sha8}"
chmod -R u+w "/srv/ci/cases/$cid" "/srv/ci/secret/$cid" "/srv/ci/work/$cid" 2>/dev/null || true   # Go makes both module caches read-only
rm -rf "/srv/ci/cases/$cid" "/srv/ci/secret/$cid" "/srv/ci/work/$cid" "cases/locks/$key"
python3 - "$cid" <<'PY'
import json, sys
for f in ("cases/repro.jsonl", "cases/prep-out/prep.jsonl"):
    try: rows = open(f).read().splitlines()
    except OSError: continue
    keep = lambda l: sys.argv[1] not in l          # robust to non-JSON lines (PREP_FAIL ...) and blank lines
    open(f, "w").write("".join(l + "\n" for l in rows if l.strip() and keep(l)))
PY
echo "reset $cid"
