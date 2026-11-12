#!/usr/bin/env bash
# Records terminal captures as asciinema casts (text; the source of truth of each capture) into capture/casts/.
# The commands run for real on the lab machines; see captures.json for the list and setup.sh for the pods they need.
# capture/casts/ holds the recordings of 2026-11-11 and is never overwritten: a new recording needs its own folder.
# usage: AIP_PROJECT=<project> CASTS=capture/casts-<run id> capture/record.sh <capture-name>...
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
cd "$(dirname "$0")/.."; CASTS="${CASTS:-capture/casts}"; mkdir -p "$CASTS"
for n in "$@"; do
  [ ! -e "$CASTS/$n.cast" ] || { echo "$CASTS/$n.cast exists; set CASTS to a new folder (e.g. CASTS=capture/casts-r4)"; exit 1; }
  asciinema rec --headless --quiet -f asciicast-v2 --window-size 76x17 -c "capture/run-one.sh $n" "$CASTS/$n.cast"
  echo "recorded $n: $(tail -1 "$CASTS/$n.cast" | cut -d, -f1 | tr -d '[') s, $(wc -l < "$CASTS/$n.cast") events"
done
