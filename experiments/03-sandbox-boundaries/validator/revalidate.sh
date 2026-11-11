#!/usr/bin/env bash
# Runs ON aip-kata-01. Re-checks stored patches with the current validator, plus the negative controls. No model calls.
# usage: revalidate.sh <out.jsonl> <patch files...>
set -euo pipefail
export KUBECONFIG=~/.kube/config
kubectl apply -f k8s/70-validator.yaml >/dev/null
. "$(dirname "$0")/validate.sh"
OUT="$1"; shift; : > "$OUT"; n=0
row() { python3 "$(dirname "$0")/row.py" "$1" "$2" "$OUT"; }
row "control:baseline"   "$(validate rv-baseline baseline)"
row "control:maintainer" "$(validate rv-maintainer maintainer)"
for f in validator/controls/*.diff "$@"; do n=$((n+1)); row "$f" "$(validate "rv-$n" patch "$f")"; done
