#!/usr/bin/env bash
# Runs ON aip-ci-01. The executor code (and, when present, the agent code), mounted read-only at /code in every pod.
# ci-exec: executor.py + team.py. ci-agent: agent files only (agent/ belongs to the agent worker; every file there is taken).
# ci-prep: the dependency worker.
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."
kubectl -n ci-exec create configmap ci-code --from-file=executor.py=executor/executor.py --from-file=team.py=executor/team.py -o yaml --dry-run=client | kubectl apply -f - >/dev/null
args=(); for f in agent/*; do [ -f "$f" ] && args+=(--from-file="$(basename "$f")=$f"); done
kubectl -n ci-agent create configmap ci-code "${args[@]}" -o yaml --dry-run=client | kubectl apply -f - >/dev/null
kubectl -n ci-prep create configmap ci-prep-code --from-file=prep_worker.py=cases/prep_worker.py -o yaml --dry-run=client | kubectl apply -f - >/dev/null
sha256sum executor/executor.py executor/team.py cases/prep_worker.py agent/* 2>/dev/null
