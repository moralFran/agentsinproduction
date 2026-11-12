#!/usr/bin/env bash
# Runs ON aip-kata-01. Addendum: HTTPS to a public site WITHOUT depending on DNS. The address is resolved on the node
# beforehand and pinned with `curl --resolve`, so the hostname and the TLS certificate check are kept and a timeout
# cannot be a failed name lookup. Control vs restricted, 10 repetitions, both runtimes.
# Writes results/net-https-$RUN.jsonl and results/net-https-pin-$RUN.txt.   usage: RUN=<id> diag/run-https.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh
HOST=example.com; IP=$(getent ahostsv4 "$HOST" | awk 'NR==1{print $1}'); [ -n "$IP" ]
OUT="$(out net-https jsonl)"; PIN="$(out net-https-pin txt)"; : > "$OUT"; echo "pinned $HOST -> $IP" | tee "$PIN"
probe='i=1; while [ $i -le 10 ]; do code=$(curl -s -m 5 -o /dev/null -w "%{http_code}" --resolve HOST:443:IP https://HOST/ 2>/dev/null); rc=$?; case $rc in 0) r="http_$code";; 28) r="timeout";; 7) r="conn_refused";; 6) r="dns_failure";; *) r="curl_err_$rc";; esac; echo "{\"phase\":\"PHASE\",\"runtime\":\"RT\",\"probe\":\"https_pinned_ip\",\"i\":$i,\"result\":\"$r\"}"; i=$((i+1)); done'
probe=${probe//HOST/$HOST}; probe=${probe//IP/$IP}
for RT in kata-qemu runc; do
  kubectl delete -f k8s/30-agent-netpol.yaml --ignore-not-found >/dev/null
  kubectl -n lab-agent delete pod diag --ignore-not-found --wait=true >/dev/null
  if [ "$RT" = runc ]; then grep -v runtimeClassName k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
  else sed "s/RUNTIME/$RT/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null; fi
  kubectl -n lab-agent wait --for=condition=Ready pod/diag --timeout=180s >/dev/null
  p=${probe//RT/$RT}
  kubectl -n lab-agent exec diag -- sh -c "${p//PHASE/control}" >> "$OUT"
  kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null; sleep 15
  kubectl -n lab-agent exec diag -- sh -c "${p//PHASE/restricted}" >> "$OUT"
done
kubectl -n lab-agent delete pod diag --wait=false >/dev/null
python3 diag/tally.py "$OUT"
