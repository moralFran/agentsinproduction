#!/usr/bin/env bash
# Runs ON aip-kata-01. Brings up the fixed pods the terminal captures look at; nothing here calls the model.
# The node has 4 vCPUs, so the pods come in two phases:
#   setup.sh a      diag pod (Kata), rt-runc / rt-kata (same image, only the runtime differs) and the RBAC lab;
#                   kubectl's default namespace becomes lab-agent so the commands on screen stay short
#   setup.sh b      final configuration: RBAC lab and diag pod removed, policy applied, plus "inspect": the agent's own
#                   image and pod spec with the command replaced by sleep (it has the agent's 15-minute deadline)
#   setup.sh bench  two pods with the benchmark's workload (Python process, 1 CPU, 512Mi), one per runtime, idle 15 s
#   setup.sh down   removes all of it: policy applied, no RBAC lab, default namespace back
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . ./lab.env
PY=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
show() { kubectl get pods -A | grep -v kube-system; }
case "${1:?a | b | bench | down}" in
a)
  kubectl config set-context --current --namespace=lab-agent >/dev/null
  kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
  kubectl -n lab-agent delete pod diag inspect rt-runc rt-kata --ignore-not-found --wait=true >/dev/null
  sed "s/RUNTIME/kata-qemu/" k8s/40-diag-pod.yaml | kubectl apply -f - >/dev/null
  run() { sed -e "s/POD_NAME/$1/g" -e "s/RUNTIME_LINE/$2/" -e "s/SLEEP_SECONDS/$3/" k8s/45-runtime-pod.yaml | kubectl apply -f - >/dev/null; }
  run rt-runc "" 41001                                # lab-agent enforces "restricted": the pods come from the template
  run rt-kata "runtimeClassName: kata-qemu" 42002
  kubectl create namespace lab-rbac --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  kubectl apply -f k8s/50-rbac-lab.yaml >/dev/null
  kubectl -n lab-agent wait --for=condition=Ready pod/diag pod/rt-runc pod/rt-kata --timeout=240s >/dev/null
  kubectl -n lab-rbac wait --for=condition=Ready pod/id-reader pod/id-noaccess --timeout=240s >/dev/null
  kubectl -n lab-agent cp diag/net-probe.sh diag:/tmp/net-probe.sh >/dev/null
  for id in reader noaccess; do kubectl -n lab-rbac cp diag/rbac-probe.sh "id-$id":/tmp/p.sh >/dev/null; done
  show ;;
b)
  kubectl config set-context --current --namespace=lab-agent >/dev/null
  kubectl delete namespace lab-rbac --ignore-not-found --wait=true >/dev/null
  kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
  kubectl -n lab-agent delete pod diag inspect --ignore-not-found --wait=true >/dev/null
  sed -e "s/NAME/inspect/" -e "s/RUNTIME_LINE/runtimeClassName: kata-qemu/" -e 's/"RUN_ID"/"inspect"/' -e 's/RESULT_NONCE_VALUE/none/' k8s/60-agent-pod.yaml \
    | sed -E 's/^(    image: aip-agent:[0-9]+)$/\1\n    command: ["sleep", "3600"]/' | kubectl apply -f - >/dev/null
  [ "$(kubectl -n lab-agent get pod inspect -o jsonpath='{.spec.containers[0].command[0]}')" = sleep ] || { echo "inspect would run the agent; aborting"; kubectl -n lab-agent delete pod inspect --wait=false; exit 1; }
  kubectl -n lab-agent wait --for=condition=Ready pod/inspect --timeout=240s >/dev/null
  show ;;
bench)   # the benchmark's workload, live: same image and limits as perf.py, a Python process that idles; needs phase a's diag pod gone
  kubectl -n lab-agent delete pod diag inspect rt-runc rt-kata --ignore-not-found --wait=true >/dev/null
  kubectl create namespace lab-perf --dry-run=client -o yaml | kubectl apply -f - >/dev/null    # perf.py creates it too; do not depend on it having run
  kubectl -n lab-perf delete pod bench-runc bench-kata --ignore-not-found --wait=true >/dev/null
  for rt in runc kata; do
    [ "$rt" = runc ] && rc="" || rc="runtimeClassName: kata-qemu"
    printf 'apiVersion: v1\nkind: Pod\nmetadata: {name: bench-%s, namespace: lab-perf}\nspec:\n  %s\n  automountServiceAccountToken: false\n  restartPolicy: Never\n  terminationGracePeriodSeconds: 1\n  containers:\n  - name: app\n    image: %s\n    imagePullPolicy: Never\n    command: ["python3", "-c", "import urllib.request,time; time.sleep(86400)"]\n    resources: {limits: {cpu: "1", memory: 512Mi}}\n' "$rt" "$rc" "$PY" | kubectl apply -f - >/dev/null
  done
  kubectl -n lab-perf wait --for=condition=Ready pod/bench-runc pod/bench-kata --timeout=240s >/dev/null
  sleep 15; show ;;
down)
  kubectl -n lab-perf delete pod bench-runc bench-kata --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n lab-agent delete pod diag inspect rt-runc rt-kata --ignore-not-found --wait=false >/dev/null
  kubectl delete namespace lab-rbac --ignore-not-found --wait=true >/dev/null
  kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
  kubectl config set-context --current --namespace=default >/dev/null
  show ;;
esac
