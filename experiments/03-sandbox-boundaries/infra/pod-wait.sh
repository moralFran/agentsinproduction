#!/usr/bin/env bash
# Sourced by the runners. pod_done <namespace> <pod> <timeout-seconds>
# Returns as soon as the pod's phase is Succeeded OR Failed, or when the timeout passes. `kubectl wait` takes one
# condition, and waiting only for Succeeded sat out the whole timeout whenever a pod ended as Failed. Two waits run
# side by side and the first to end stops the other. The caller reads the phase afterwards.
pod_done() {
  local ns="$1" pod="$2" t="$3" a b
  kubectl -n "$ns" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$pod" --timeout="${t}s" >/dev/null 2>&1 & a=$!
  kubectl -n "$ns" wait --for=jsonpath='{.status.phase}'=Failed    "pod/$pod" --timeout="${t}s" >/dev/null 2>&1 & b=$!
  while kill -0 "$a" 2>/dev/null && kill -0 "$b" 2>/dev/null; do sleep 0.1; done
  kill "$a" "$b" 2>/dev/null || true
  wait "$a" "$b" 2>/dev/null || true
  return 0
}
