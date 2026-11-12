#!/usr/bin/env bash
# Runs ON aip-ci-01. Records captures listed in capture/captures.json as asciinema casts (76x17, the channel's terminal
# size) into capture/casts/. The commands run for real here; only the typing is simulated by play.py.
# usage: capture/record.sh <capture-name>...
set -euo pipefail
cd "$(dirname "$0")/.."; mkdir -p capture/casts
[ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
command -v asciinema >/dev/null || { sudo apt-get install -y -qq asciinema >/dev/null; }
for n in "$@"; do
  rm -f "capture/casts/$n.cast"
  asciinema rec -q --overwrite --cols 76 --rows 17 -c "python3 -u capture/play.py $n" "capture/casts/$n.cast" </dev/null >/dev/null 2>&1 || \
  asciinema rec -q --overwrite -c "stty cols 76 rows 17; python3 -u capture/play.py $n" "capture/casts/$n.cast" </dev/null >/dev/null 2>&1
  echo "recorded $n: $(tail -1 "capture/casts/$n.cast" | cut -d, -f1 | tr -d '[') s"
done
