#!/usr/bin/env bash
# Runs ON aip-kata-01. The gateway's handling of untrusted clients, live, from a pod with the agent's image and spec
# (command replaced by sleep): bad Content-Length, wrong type, a body and headers that never complete, the connection
# limit per source, the pinned version header. One Haiku call. Writes results/gateway-live-$RUN.jsonl, then the
# gateway's own log lines for these requests.   usage: RUN=<id> diag/run-gateway-live.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh
OUT="$(out gateway-live jsonl)"
kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
kubectl -n lab-agent delete pod gwlive --ignore-not-found --wait=true >/dev/null
trap 'kubectl -n lab-agent delete pod gwlive --ignore-not-found --wait=false >/dev/null 2>&1 || true' EXIT
sed -e "s/NAME/gwlive/" -e "s/RUNTIME_LINE/runtimeClassName: kata-qemu/" -e 's/"RUN_ID"/"gwlive"/' -e 's/RESULT_NONCE_VALUE/none/' k8s/60-agent-pod.yaml \
  | sed -E 's/^(    image: aip-agent:[0-9]+)$/\1\n    command: ["sleep", "900"]/' | kubectl apply -f - >/dev/null
[ "$(kubectl -n lab-agent get pod gwlive -o jsonpath='{.spec.containers[0].command[0]}')" = sleep ] || { echo "gwlive pod would run the agent; aborting"; exit 1; }
kubectl -n lab-agent wait --for=condition=Ready pod/gwlive --timeout=180s >/dev/null
# the script goes in as an argument, not on stdin: with stdin, kubectl exec stopped relaying the pod's output once
# stdin closed while the script kept running (run r4: one line of six reached the file)
kubectl -n lab-agent exec gwlive -- python3 -c "$(cat diag/gateway-live.py)" | tee "$OUT"
echo "== the gateway's log for these requests"
kubectl -n lab-gateway logs deploy/gateway --tail=40 | grep -E 'gateway-live|read_deadline|too many open' | tail -12 || true
python3 - "$OUT" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
print(f"{sum(r['ok'] for r in rows)}/{len(rows)} checks as expected"); sys.exit(0 if rows and all(r["ok"] for r in rows) else 1)
PY
