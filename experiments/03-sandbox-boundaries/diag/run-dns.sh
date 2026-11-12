#!/usr/bin/env bash
# Runs ON aip-kata-01. Addendum to the network diagnostic: name resolution (UDP 53 to the cluster DNS and to a public
# resolver), control vs restricted, 10 repetitions, kata-qemu. The policy has no DNS rule, so both should be blocked.
# Writes results/net-dns-$RUN.jsonl.   usage: RUN=<id> diag/run-dns.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh
OUT="$(out net-dns jsonl)"; : > "$OUT"
probe='for i in 1 2 3 4 5 6 7 8 9 10; do for s in 10.43.0.10 8.8.8.8; do if timeout 4 nslookup example.com $s >/dev/null 2>&1; then r=resolved; else r=no_answer; fi; echo "{\"phase\":\"PHASE\",\"runtime\":\"kata-qemu\",\"probe\":\"dns_$s\",\"i\":$i,\"result\":\"$r\"}"; done; done'
kubectl delete -f k8s/30-agent-netpol.yaml --ignore-not-found >/dev/null
kubectl -n lab-agent delete pod diag --ignore-not-found --wait=true >/dev/null
sed "s/RUNTIME/kata-qemu/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
kubectl -n lab-agent wait --for=condition=Ready pod/diag --timeout=180s >/dev/null
kubectl -n lab-agent exec diag -- sh -c "${probe//PHASE/control}" >> "$OUT"
kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null; sleep 15
kubectl -n lab-agent exec diag -- sh -c "${probe//PHASE/restricted}" >> "$OUT"
kubectl -n lab-agent delete pod diag --wait=false >/dev/null
python3 diag/tally.py "$OUT"
