#!/usr/bin/env bash
# Runs ON aip-ci-01. The executor and agent code, mounted read-only at /code in every pod (both namespaces).
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."
for ns in ci-exec ci-agent; do
  args=(--from-file=executor.py=executor/executor.py); [ -f agent/agent.py ] && args+=(--from-file=agent.py=agent/agent.py)
  [ "$ns" = ci-agent ] && args=(--from-file=agent.py=agent/agent.py --from-file=prompt-v1.txt=agent/prompt-v1.txt --from-file=prompt-v2.txt=agent/prompt-v2.txt)
  kubectl -n "$ns" create configmap ci-code "${args[@]}" -o yaml --dry-run=client | kubectl apply -f - >/dev/null
done
sha256sum executor/executor.py agent/agent.py agent/prompt-v1.txt agent/prompt-v2.txt 2>/dev/null

kubectl -n ci-prep create configmap ci-prep-code --from-file=prep_worker.py=cases/prep_worker.py -o yaml --dry-run=client | kubectl apply -f - >/dev/null
