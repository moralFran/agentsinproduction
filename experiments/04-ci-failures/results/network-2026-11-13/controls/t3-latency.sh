#!/usr/bin/env bash
# T3 (2026-11-13), runs ON the VM. Experiment 03's scenario, timed: a pod is already running in a namespace WITHOUT a
# policy and probes every 0.05 s; 8 s after it is Running the policy is applied with `kubectl apply` (time recorded
# before and after the command); the probe log shows when each destination stopped answering. Then the policy is
# deleted and the next repetition starts. usage: t3-latency.sh <namespace> <kata|runc> <repetitions> <out-dir>
export KUBECONFIG=~/.kube/config; ns="$1"; rt="$2"; n="$3"; out="$4"; here="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$out"
"$here/t3-namespace.sh" "$ns" > /dev/null
for i in $(seq 1 "$n"); do
  name="t3lat-$rt-$i"
  echo "{\"concurrency\": 1, \"pods\": [{\"name\": \"$name\", \"kind\": \"agent\", \"runtime\": \"$rt\", \"gate\": false, \"seconds\": 30, \"interval\": 0.05, \"timeout\": 0.15, \"ns\": \"$ns\"}]}" > "$out/plan-$name.json"
  python3 "$here/run-watch-pods.py" ~/run gobwas-ws-a567dfd6 "$out" ~/lab/results/patches/v1/v1-e88f0806-r1.diff "$out/plan-$name.json" >> "$out/driver-$rt.log" 2>&1 &
  sleep 1; "$here/t3-apply-when-running.sh" "$ns" 8 "$out/apply-times.jsonl" "$name"
  wait
  a=$(date +%s%3N); kubectl -n "$ns" delete networkpolicy agent-egress-gateway-only > /dev/null; echo "{\"ns\": \"$ns\", \"after\": \"$name\", \"policy_deleted_ms\": $a}" >> "$out/apply-times.jsonl"
  sleep 4
done
echo "$(date -u +%T) T3_LATENCY_DONE $rt" >> "$out/driver-$rt.log"
