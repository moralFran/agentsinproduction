#!/usr/bin/env bash
# Starts a FRESH run of experiment 04 in a new folder, so the historical record (this folder: cases.csv, the attempts, the
# packets, the verdicts) is never written to. Copies the code only; no record. Added 2026-11-12, after the collection.
#   usage: infra/new-run.sh <new-dir> [--with-candidates]
#   --with-candidates  also copies mining/candidates-{go,python}.jsonl, to prepare and reproduce the SAME 113 candidates
#                      and their sanitized mining logs for funnel.py, instead of mining again (GitHub's search and its
#                      log retention change over time); the archived
#                      cases.csv sha256 is copied to cases/archived-cases.csv.sha256 for comparison after freeze.py.
# Then run everything from <new-dir> exactly as the README says. The scripts that write records refuse to run in a folder
# that has an ARCHIVE file (set ALLOW_ARCHIVE_WRITE=1 to override); the new folder has none.
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)"; dst="${1:?usage: infra/new-run.sh <new-dir> [--with-candidates]}"
dst="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$dst")"
case "$dst/" in "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$src")/"*) echo "refusing: $dst is inside the archived folder $src" >&2; exit 1;; esac
mkdir -p "$dst"
[ -z "$(ls -A "$dst")" ] || { echo "refusing: $dst is not empty" >&2; exit 1; }
cd "$src"
files=(agent/agent.py agent/prompt-v1.txt agent/prompt-v2.txt executor/executor.py executor/test_executor.py
       gateway/gateway.py gateway/test_budget.py k8s/00-base.yaml k8s/10-gateway.yaml judge/server.py judge/page.html judge/start.sh
       mining/mine.py results/analyze.py results/blind/codex-review-2026-11-12/writer_review_test.go
       capture/captures.json capture/play.py capture/record.sh criteria.md FUTURE-RUNS.md infra/test_security.py)
files+=(infra/*.sh infra/Dockerfile.box cases/*.py cases/*.sh)
[ "${2:-}" = --with-candidates ] && files+=(mining/candidates-go.jsonl mining/candidates-python.jsonl
                                         mining/candidates-go.log mining/candidates-python.log)
for f in "${files[@]}"; do mkdir -p "$dst/$(dirname "$f")"; cp -p "$f" "$dst/$f"; done
[ "${2:-}" = --with-candidates ] && cp cases/cases.csv.sha256 "$dst/cases/archived-cases.csv.sha256"
# New judgments start without exclusions; never inherit the historical run's decisions.
mkdir -p "$dst/results/blind"
printf '{}\n' > "$dst/results/blind/excluded.json"
printf 'Fresh run started %s from %s (code only%s). Not the historical record.\n' "$(date -u +%FT%TZ)" "$src" \
  "$([ "${2:-}" = --with-candidates ] && echo ', plus the 113 archived candidates and their mining logs')" > "$dst/FRESH_RUN"
echo "fresh run folder: $dst ($(find "$dst" -type f | wc -l | tr -d ' ') files)"
