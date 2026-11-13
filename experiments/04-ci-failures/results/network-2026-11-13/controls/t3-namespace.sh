#!/usr/bin/env bash
# T3 (2026-11-13), runs ON the VM. Makes a namespace with NO NetworkPolicy that can run pods built by cases/pod.py
# (service account "runner", the code ConfigMap, the probe ConfigMap). usage: t3-namespace.sh <namespace>
export KUBECONFIG=~/.kube/config; ns="$1"; here="$(cd "$(dirname "$0")" && pwd)"
kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
printf 'apiVersion: v1\nkind: ServiceAccount\nmetadata: {name: runner, namespace: %s}\nautomountServiceAccountToken: false\n' "$ns" | kubectl apply -f - >/dev/null
kubectl -n ci-agent get configmap ci-code -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"ci-code","namespace":sys.argv[1]},"data":d["data"]}))' "$ns" | kubectl apply -f - >/dev/null
kubectl -n "$ns" create configmap probe-code --from-file="$here/netwatch.py" -o yaml --dry-run=client | kubectl apply -f - >/dev/null
kubectl -n "$ns" get sa,configmap --no-headers | tr '\n' ' '; echo
