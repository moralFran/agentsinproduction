#!/usr/bin/env bash
# Runs ON aip-kata-01. Same workload, image, limits and policy; only the runtime changes. Evidence of which
# architecture is running: RuntimeClass on the pod, the sandbox's runtime handler, the host process tree, and
# whether the workload's process exists on the host's kernel. This checks architecture; it runs no exploit.
set -euo pipefail
export KUBECONFIG=~/.kube/config
OUT="${1:-results/runtime.txt}"; : > "$OUT"
echo "host kernel: $(uname -r)" | tee -a "$OUT"
for RT in runc kata-qemu; do
  n="rt-${RT%%-*}"; marker=$((RANDOM + 40000))
  if [ "$RT" = runc ]; then ov='{"spec":{"automountServiceAccountToken":false}}'; else ov='{"spec":{"automountServiceAccountToken":false,"runtimeClassName":"'$RT'"}}'; fi
  kubectl -n lab-agent delete pod "$n" --ignore-not-found >/dev/null
  kubectl -n lab-agent run "$n" --image=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b --restart=Never --labels=app=agent --overrides="$ov" -- sleep "$marker" >/dev/null
  kubectl -n lab-agent wait --for=condition=Ready pod/"$n" --timeout=180s >/dev/null
  sid=$(sudo crictl pods --name "$n" --state Ready -q --no-trunc | head -1)
  {
    echo; echo "== $RT (pod $n, sandbox ${sid:0:12})"
    echo "pod.spec.runtimeClassName: $(kubectl -n lab-agent get pod "$n" -o jsonpath='{.spec.runtimeClassName}')"
    echo "sandbox runtime handler:   $(sudo crictl inspectp "$sid" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["info"].get("runtimeHandler") or d["status"].get("runtimeHandler") or "(default)")')"
    echo "kernel seen by the pod:    $(kubectl -n lab-agent exec "$n" -- uname -r)"
    echo "cpu 'hypervisor' flag in the pod: $(kubectl -n lab-agent exec "$n" -- sh -c 'grep -c -m1 hypervisor /proc/cpuinfo || true')"
    echo "pod's memory (MemTotal):   $(kubectl -n lab-agent exec "$n" -- sh -c 'grep MemTotal /proc/meminfo' | tr -s ' ')"
    echo "workload process 'sleep $marker' visible in the HOST process table: $(pgrep -f "sleep $marker" | grep -v $$ | wc -l)"
    echo "host processes whose command line names this sandbox:"
    ps -eo pid,comm,args | grep "$sid" | grep -v grep | awk '{print "  " $1, $2}'
  } | tee -a "$OUT"
  kubectl -n lab-agent delete pod "$n" --wait=false >/dev/null
done
