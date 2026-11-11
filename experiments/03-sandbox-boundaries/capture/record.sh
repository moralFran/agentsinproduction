#!/usr/bin/env bash
# Records terminal captures as asciinema casts (text; the source of truth of each capture) into capture/casts/.
# The commands run for real on the lab machines; see captures.json for the list and setup.sh for the pods they need.
# usage: AIP_PROJECT=<project> capture/record.sh <capture-name>...
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
cd "$(dirname "$0")/.."; mkdir -p capture/casts
for n in "$@"; do
  rm -f "capture/casts/$n.cast"
  asciinema rec --headless --quiet -f asciicast-v2 --window-size 76x17 -c "capture/run-one.sh $n" "capture/casts/$n.cast"
  echo "recorded $n: $(tail -1 "capture/casts/$n.cast" | cut -d, -f1 | tr -d '[') s, $(wc -l < "capture/casts/$n.cast") events"
done
