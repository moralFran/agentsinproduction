#!/usr/bin/env bash
# Runs ON aip-kata-01. Who can reach the gateway: a pod in the agent's position, and a pod in ANOTHER namespace
# ("outsider"), first without the ingress policy (control: both reach it) and then with it (k8s/15-gateway-ingress.yaml:
# only the agent's pods may). 10 repetitions each; no model call (GET /healthz, and GET /v1/models which the gateway
# itself answers 403). Leaves the policy applied. Writes results/gateway-ingress-$RUN.jsonl.
# usage: RUN=<id> diag/run-gateway-ingress.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh
OUT="$(out gateway-ingress jsonl)"; : > "$OUT"
CURL=curlimages/curl:8.11.1@sha256:c1fe1679c34d9784c1b0d1e5f62ac0a79fca01fb6377cdd33e90473c6f9f9a69
cleanup() { kubectl apply -f k8s/15-gateway-ingress.yaml >/dev/null 2>&1 || true; kubectl delete namespace lab-other --ignore-not-found --wait=false >/dev/null 2>&1 || true
            kubectl -n lab-agent delete pod diag --ignore-not-found --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT
kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
kubectl -n lab-agent delete pod diag --ignore-not-found --wait=true >/dev/null
sed "s/RUNTIME/kata-qemu/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
kubectl create namespace lab-other --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n lab-other delete pod outsider --ignore-not-found --wait=true >/dev/null
kubectl -n lab-other run outsider --image="$CURL" --restart=Never --command -- sleep 3600 >/dev/null
kubectl -n lab-agent wait --for=condition=Ready pod/diag --timeout=180s >/dev/null
kubectl -n lab-other wait --for=condition=Ready pod/outsider --timeout=180s >/dev/null
probe='i=1; while [ $i -le 10 ]; do for p in healthz v1/models; do code=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://10.43.200.10:8080/$p 2>/dev/null); rc=$?; case $rc in 0) r="http_$code";; 28) r="timeout";; 7) r="conn_refused";; *) r="curl_err_$rc";; esac; echo "{\"phase\":\"PHASE\",\"runtime\":\"FROM\",\"probe\":\"gateway /$p\",\"i\":$i,\"result\":\"$r\"}"; done; i=$((i+1)); done'
both() { local p="${probe//PHASE/$1}"
         kubectl -n lab-agent exec diag     -- sh -c "${p//FROM/agent-pod}" >> "$OUT"
         kubectl -n lab-other exec outsider -- sh -c "${p//FROM/other-namespace}" >> "$OUT"; }
kubectl delete -f k8s/15-gateway-ingress.yaml --ignore-not-found >/dev/null; sleep 15
echo "[no ingress policy: control]"; both control
kubectl apply -f k8s/15-gateway-ingress.yaml >/dev/null; sleep 15
echo "[with the ingress policy]";    both restricted
python3 diag/tally.py "$OUT"
