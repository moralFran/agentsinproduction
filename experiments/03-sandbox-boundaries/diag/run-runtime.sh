#!/usr/bin/env bash
# Runs ON aip-kata-01. Same workload, image, security settings and policy; only the runtime changes
# (k8s/45-runtime-pod.yaml). Evidence of which architecture is running: RuntimeClass on the pod, the sandbox's runtime
# handler, the host process tree, and whether the workload's process exists on the host's kernel. Also what the
# kernel reports about seccomp for the pod's process. This checks architecture; it runs no exploit.
# Writes results/runtime-$RUN.txt.   usage: RUN=<id> diag/run-runtime.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh
OUT="$(out runtime txt)"; : > "$OUT"
echo "host kernel: $(uname -r)" | tee -a "$OUT"
for RT in runc kata-qemu; do
  n="rt-${RT%%-*}"; marker=$((RANDOM + 40000))
  if [ "$RT" = runc ]; then line=""; else line="runtimeClassName: $RT"; fi
  kubectl -n lab-agent delete pod "$n" --ignore-not-found >/dev/null
  sed -e "s/POD_NAME/$n/g" -e "s/RUNTIME_LINE/$line/" -e "s/SLEEP_SECONDS/$marker/" k8s/45-runtime-pod.yaml | kubectl apply -f - >/dev/null
  kubectl -n lab-agent wait --for=condition=Ready pod/"$n" --timeout=180s >/dev/null
  sid=$(sudo crictl pods --name "$n" --state Ready -q --no-trunc | head -1)
  {
    echo; echo "== $RT (pod $n, sandbox ${sid:0:12})"
    echo "pod.spec.runtimeClassName: $(kubectl -n lab-agent get pod "$n" -o jsonpath='{.spec.runtimeClassName}')"
    echo "sandbox runtime handler:   $(sudo crictl inspectp "$sid" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["info"].get("runtimeHandler") or d["status"].get("runtimeHandler") or "(default)")')"
    echo "kernel seen by the pod:    $(kubectl -n lab-agent exec "$n" -- uname -r)"
    echo "cpu 'hypervisor' flag in the pod: $(kubectl -n lab-agent exec "$n" -- sh -c 'grep -c -m1 hypervisor /proc/cpuinfo || true')"
    echo "pod's memory (MemTotal):   $(kubectl -n lab-agent exec "$n" -- sh -c 'grep MemTotal /proc/meminfo' | tr -s ' ')"
    echo "pod's process, user and seccomp mode (0 none, 2 filter): uid $(kubectl -n lab-agent exec "$n" -- id -u), $(kubectl -n lab-agent exec "$n" -- sh -c 'grep "^Seccomp:" /proc/1/status' | tr -s '\t ' ' ')"
    echo "workload process 'sleep $marker' visible in the HOST process table: $(pgrep -f "sleep $marker" | grep -v $$ | wc -l)"
    echo "host processes whose command line names this sandbox:"
    ps -eo pid,comm,args | grep "$sid" | grep -v grep | awk '{print "  " $1, $2}'
  } | tee -a "$OUT"
  kubectl -n lab-agent delete pod "$n" --wait=false >/dev/null
done
