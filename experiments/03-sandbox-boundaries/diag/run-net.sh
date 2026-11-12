#!/usr/bin/env bash
# Runs ON aip-kata-01. For each runtime: control phase (no NetworkPolicy), then the restricted phase, N repetitions
# each (10 unless N is set). Writes results/net-$RUN.jsonl.   usage: RUN=<id> [N=<repetitions>] diag/run-net.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . ./lab.env; . infra/out.sh
N="${N:-10}"; OUT="$(out net jsonl)"; : > "$OUT"
for RT in kata-qemu runc; do
  kubectl delete -f k8s/30-agent-netpol.yaml --ignore-not-found >/dev/null
  kubectl -n lab-agent delete pod diag --ignore-not-found --wait=true >/dev/null
  if [ "$RT" = runc ]; then grep -v runtimeClassName k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
  else sed "s/RUNTIME/$RT/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null; fi
  kubectl -n lab-agent wait --for=condition=Ready pod/diag --timeout=180s >/dev/null
  kubectl -n lab-agent cp diag/net-probe.sh diag:/tmp/net-probe.sh >/dev/null
  echo "[$RT] control";    kubectl -n lab-agent exec diag -- sh /tmp/net-probe.sh control "$RT" "$N" "$ENDPOINT_IP" "$NODE_IP" >> "$OUT"
  kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null; sleep 15   # give the policy controller time to program rules
  echo "[$RT] restricted"; kubectl -n lab-agent exec diag -- sh /tmp/net-probe.sh restricted "$RT" "$N" "$ENDPOINT_IP" "$NODE_IP" >> "$OUT"
done
kubectl -n lab-agent delete pod diag --wait=false >/dev/null
wc -l "$OUT"
