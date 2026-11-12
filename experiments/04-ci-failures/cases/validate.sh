#!/usr/bin/env bash
# Runs ON aip-ci-01. Runs the executor's mandatory checks on a given patch for a case and prints the verdict.
# usage: validate.sh <case-id> <patch.diff>
set -euo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
python3 cases/pod.py exec "$1" "vc-$(echo "$1$2" | md5sum | cut -c1-8)" 2400 --patch "$2" -- python3 -u /code/executor.py validate \
  | grep '^EXECUTOR ' | sed 's/^EXECUTOR //' | python3 -c 'import json,sys; r=json.load(sys.stdin); print("outcome:", r.get("outcome")); print("why:", r.get("why", "-")[:70]); print("tests run:", "suite_runs" in r)'
