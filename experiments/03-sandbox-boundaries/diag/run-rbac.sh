#!/usr/bin/env bash
# Runs ON aip-kata-01. Effective permissions (kubectl auth can-i) and real API answers for the two identities.
set -euo pipefail
export KUBECONFIG=~/.kube/config
OUT="${1:-results/rbac.jsonl}"; : > "$OUT"
kubectl apply -f k8s/50-rbac-lab.yaml >/dev/null
kubectl -n lab-rbac wait --for=condition=Ready pod/id-reader pod/id-noaccess --timeout=180s >/dev/null
for id in reader noaccess; do
  for q in "get secret/dummy-credentials -n lab-rbac" "list secrets -n lab-rbac" "get secret/gateway-key -n lab-gateway"; do
    echo "can-i $id: $q => $(kubectl auth can-i $q --as=system:serviceaccount:lab-rbac:$id 2>/dev/null || true)"
  done
  kubectl -n lab-rbac cp diag/rbac-probe.sh id-$id:/tmp/p.sh >/dev/null
  kubectl -n lab-rbac exec id-$id -- sh /tmp/p.sh "$id" 10 >> "$OUT"
done
kubectl -n lab-rbac delete pod id-reader id-noaccess --wait=false >/dev/null
