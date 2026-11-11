#!/usr/bin/env bash
# Runs one capture where it belongs. Called by record.sh inside asciinema; the project id stays in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."; n="${1:?capture name}"; ZONE="${ZONE:-us-central1-a}"
where=$(python3 -c 'import json,sys; print(json.load(open("capture/captures.json"))["captures"][sys.argv[1]]["where"])' "$n")
case "$where" in
  mac)      exec python3 -u capture/play.py "$n" ;;
  vm)       exec gcloud compute ssh aip-kata-01 --project "$AIP_PROJECT" --zone "$ZONE" --command "python3 -u capture/play.py $n" 2>/dev/null ;;
  endpoint) exec gcloud compute ssh aip-endpoint-01 --project "$AIP_PROJECT" --zone "$ZONE" --command "python3 -u capture/play.py $n" 2>/dev/null ;;
esac
