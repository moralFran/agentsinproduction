#!/usr/bin/env bash
# Runs ON aip-kata-01. Checks that the limits are enforced from OUTSIDE the agent. One tiny Haiku call; no Sonnet.
# 1. Pod deadline: the agent's own pod spec with a command that never ends and a 20 s deadline must be killed.
# 2. Gateway in the cluster: forwards a valid call, books it, and still has it booked after a restart.
# 3. Gateway budget in the cluster: with the budget below the cost of one call, the call is refused, not forwarded.
# 4. Request format in the cluster: an image by URL is refused before it is forwarded; nothing is booked.
# (Killing the gateway mid-call and a state that cannot be written are tested offline: gateway/test_budget.py.)
# Step 3 changes the gateway's budget. Whatever happens after that, the EXIT trap puts back the value found at the
# start and removes the test pod. Writes results/limits-$RUN.txt.   usage: RUN=<id> diag/run-limits.sh
# FAIL_AFTER_LOWERING=1 makes the script stop right after lowering the budget, to see the trap work.
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . ./lab.env; . infra/out.sh
OUT="$(out limits txt)"; : > "$OUT"
budget() { kubectl -n lab-gateway get deploy gateway -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="BUDGET_USD")].value}'; }
ORIG="$(budget)"; [ -n "$ORIG" ] || { echo "cannot read the gateway's BUDGET_USD"; exit 1; }
restore() {
  kubectl -n lab-agent delete pod deadline-test --ignore-not-found --wait=false >/dev/null 2>&1 || true
  if [ "$(budget 2>/dev/null)" != "$ORIG" ]; then
    kubectl -n lab-gateway set env deploy/gateway BUDGET_USD="$ORIG" >/dev/null || true
    kubectl -n lab-gateway rollout status deploy/gateway --timeout=240s >/dev/null || true
    echo "gateway budget put back to $ORIG (now: $(budget 2>/dev/null))"
  fi
}
trap restore EXIT
kubectl -n lab-agent delete pod deadline-test --ignore-not-found >/dev/null
sed -e "s/NAME/deadline-test/" -e "s/RUNTIME_LINE/runtimeClassName: kata-qemu/" -e 's/"RUN_ID"/"deadline-test"/' -e 's/RESULT_NONCE_VALUE/none/' -e "s/activeDeadlineSeconds: [0-9]*/activeDeadlineSeconds: 20/" k8s/60-agent-pod.yaml \
  | sed -E 's/^(    image: aip-agent:[0-9]+)$/\1\n    command: ["sleep", "3600"]/' | kubectl apply -f - >/dev/null
[ "$(kubectl -n lab-agent get pod deadline-test -o jsonpath='{.spec.containers[0].command[0]}{.spec.activeDeadlineSeconds}')" = sleep20 ] || { echo "deadline-test pod is not the sleep/20 s variant; aborting"; exit 1; }
t0=$(date +%s); kubectl -n lab-agent wait --for=jsonpath='{.status.phase}'=Failed pod/deadline-test --timeout=120s >/dev/null 2>&1 || true
echo "1. pod with a 20 s deadline running 'sleep 3600': phase=$(kubectl -n lab-agent get pod deadline-test -o jsonpath='{.status.phase}') reason=$(kubectl -n lab-agent get pod deadline-test -o jsonpath='{.status.reason}') after $(( $(date +%s) - t0 )) s" | tee -a "$OUT"
kubectl -n lab-agent delete pod deadline-test --wait=false >/dev/null
call() { kubectl -n lab-gateway exec deploy/gateway -- python3 -c '
import json, urllib.request, urllib.error
d = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 8, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]}).encode()
try: print(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8080/v1/messages", data=d, headers={"x-run-id": "limits-check"}), timeout=60).status)
except urllib.error.HTTPError as e: print(e.code, e.read().decode()[:120])'; }
state() { kubectl -n lab-gateway exec deploy/gateway -- cat /state/budget.json; }
echo "2. valid call through the gateway: HTTP $(call)" | tee -a "$OUT"
before=$(state); kubectl -n lab-gateway rollout restart deploy/gateway >/dev/null; kubectl -n lab-gateway rollout status deploy/gateway --timeout=240s >/dev/null
echo "   booked before restart: $before" | tee -a "$OUT"; echo "   booked after restart:  $(state)" | tee -a "$OUT"
kubectl -n lab-gateway set env deploy/gateway BUDGET_USD=0.000001 >/dev/null; kubectl -n lab-gateway rollout status deploy/gateway --timeout=240s >/dev/null
[ -z "${FAIL_AFTER_LOWERING:-}" ] || { echo "stopping on purpose with the test budget in place (FAIL_AFTER_LOWERING is set): the trap must put it back"; exit 1; }
echo "3. same call with the budget set to \$0.000001: HTTP $(call)" | tee -a "$OUT"
echo "   booked after the refused call: $(state)" | tee -a "$OUT"
kubectl -n lab-gateway set env deploy/gateway BUDGET_USD="$ORIG" >/dev/null; kubectl -n lab-gateway rollout status deploy/gateway --timeout=240s >/dev/null
echo "   budget put back to: $(budget)" | tee -a "$OUT"
img() { kubectl -n lab-gateway exec deploy/gateway -- env ENDPOINT_IP="$ENDPOINT_IP" python3 -c '
import json, os, urllib.request, urllib.error
d = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 8, "messages": [{"role": "user", "content": [{"type": "image", "source": {"type": "url", "url": "http://" + os.environ["ENDPOINT_IP"] + ":8080/probe/image-by-url"}}]}]}).encode()
try: print(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8080/v1/messages", data=d, headers={"x-run-id": "limits-check"}), timeout=60).status)
except urllib.error.HTTPError as e: print(e.code, e.read().decode()[:120])'; }
before=$(state)
echo "4. message with an image by URL: HTTP $(img)" | tee -a "$OUT"
echo "   booked before: $before" | tee -a "$OUT"; echo "   booked after:  $(state)" | tee -a "$OUT"
kubectl -n lab-gateway logs deploy/gateway | tail -2 | tee -a "$OUT"
