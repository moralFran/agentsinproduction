#!/usr/bin/env bash
# Runs ON aip-kata-01. Re-checks stored patches with the current validator, plus the negative controls. No model calls.
# usage: revalidate.sh <out.jsonl> <patch files...>      (the output file must not exist: a run never overwrites one)
set -euo pipefail
export KUBECONFIG=~/.kube/config
cd "$(dirname "$0")/.."
OUT="${1:?output file, e.g. results/revalidation-r4.jsonl}"; shift
[ ! -e "$OUT" ] || { echo "$OUT already exists; pick a new name"; exit 1; }
kubectl apply -f k8s/70-validator.yaml >/dev/null
. validator/validate.sh
: > "$OUT"; n=0
row() { python3 validator/row.py "$1" "$2" "$OUT"; }
row "control:baseline"   "$(validate rv-baseline baseline)"
row "control:maintainer" "$(validate rv-maintainer maintainer)"
for f in validator/controls/*.diff "$@"; do n=$((n+1)); row "$f" "$(validate "rv-$n" patch "$f")"; done
