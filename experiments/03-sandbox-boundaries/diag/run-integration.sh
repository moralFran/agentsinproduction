#!/usr/bin/env bash
# Runs ON aip-kata-01. Final configuration: NetworkPolicy applied, RBAC lab removed, agent pod spec as used for the task.
# Repeats the network diagnostic from the agent's position and inspects what is inside the agent's own container.
# Writes results/net-final-$RUN.jsonl and results/integration-$RUN.txt.   usage: RUN=<id> diag/run-integration.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . ./lab.env; . infra/out.sh
NET="$(out net-final jsonl)"; TXT="$(out integration txt)"
kubectl delete namespace lab-rbac --ignore-not-found --wait=true >/dev/null          # diagnostic identities and tokens gone
kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
kubectl -n lab-agent delete pod diag inspect --ignore-not-found --wait=true >/dev/null
sed "s/RUNTIME/kata-qemu/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
kubectl -n lab-agent wait --for=condition=Ready pod/diag --timeout=180s >/dev/null
kubectl -n lab-agent cp diag/net-probe.sh diag:/tmp/net-probe.sh >/dev/null
kubectl -n lab-agent exec diag -- sh /tmp/net-probe.sh final kata-qemu 10 "$ENDPOINT_IP" "$NODE_IP" > "$NET"
python3 diag/tally.py "$NET"
# the agent's own image and pod spec, with the command replaced by an inspection
sed -e "s/NAME/inspect/" -e "s/RUNTIME_LINE/runtimeClassName: kata-qemu/" -e 's/"RUN_ID"/"inspect"/' -e 's/RESULT_NONCE_VALUE/none/' k8s/60-agent-pod.yaml \
  | sed -E 's/^(    image: aip-agent:[0-9]+)$/\1\n    command: ["sleep", "600"]/' | kubectl apply -f - >/dev/null
[ "$(kubectl -n lab-agent get pod inspect -o jsonpath='{.spec.containers[0].command[0]}')" = sleep ] || { echo "inspect pod would run the agent; aborting"; kubectl -n lab-agent delete pod inspect --wait=false; exit 1; }
kubectl -n lab-agent wait --for=condition=Ready pod/inspect --timeout=180s >/dev/null
{
  echo "== inside the agent's container (final spec, kata-qemu)"
  kubectl -n lab-agent exec inspect -- sh -c '
    echo "user: $(id -u):$(id -g)"
    echo "env vars whose NAME mentions key/token/secret/password: $(env | cut -d= -f1 | grep -i -c -E "key|token|secret|password" || true)"
    echo "env names: $(env | cut -d= -f1 | sort | tr "\n" " ")"
    echo "service-account token dir exists: $([ -e /var/run/secrets/kubernetes.io/serviceaccount ] && echo yes || echo no)"
    echo "CapEff: $(grep CapEff /proc/self/status | cut -f2)   NoNewPrivs: $(grep NoNewPrivs /proc/self/status | cut -f2)   Seccomp: $(grep "^Seccomp:" /proc/self/status | cut -f2)"
    echo "root filesystem writable: $(touch /probe-write 2>/dev/null && echo yes || echo no)"
    echo "kernel: $(uname -r)"'
  diag/reach.sh inspect
} | tee "$TXT"
kubectl -n lab-agent delete pod diag inspect --wait=false >/dev/null
echo "namespaces: $(kubectl get ns -o name | grep lab- | tr '\n' ' ')" | tee -a "$TXT"
