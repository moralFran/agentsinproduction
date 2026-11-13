#!/usr/bin/env bash
# T3 (2026-11-13), runs ON the VM. Waits until every named pod of <namespace> has been Running for <wait> seconds, then
# applies the policy and writes the epoch-ms time just before and just after `kubectl apply` returned.
# usage: t3-apply-when-running.sh <namespace> <wait_s> <out-file> <pod>...
export KUBECONFIG=~/.kube/config; ns="$1"; wait="$2"; out="$3"; shift 3; here="$(cd "$(dirname "$0")" && pwd)"
for p in "$@"; do until [ "$(kubectl -n "$ns" get pod "$p" -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]; do sleep 0.5; done; done
sleep "$wait"; a=$(date +%s%3N); sed "s/NAMESPACE/$ns/" "$here/t3-policy.yaml" | kubectl apply -f - >/dev/null; b=$(date +%s%3N)
echo "{\"ns\": \"$ns\", \"pods\": \"$*\", \"apply_start_ms\": $a, \"apply_end_ms\": $b}" >> "$out"
