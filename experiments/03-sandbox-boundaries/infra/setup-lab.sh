#!/usr/bin/env bash
# Runs ON aip-kata-01, from the experiment folder, after install-k3s-kata.sh. Prepares everything the diagnostics need:
# namespaces, the code ConfigMaps, the fake internal API, the gateway (key read from STDIN, never from a file) and the
# images. The test endpoint is started separately on aip-endpoint-01 (see README).
# usage: <key on stdin> | infra/setup-lab.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config
kubectl apply -f k8s/00-namespaces.yaml
kubectl -n lab-gateway  create configmap gateway-code      --from-file=gateway/gateway.py      -o yaml --dry-run=client | kubectl apply -f -
kubectl -n lab-internal create configmap internal-api-code --from-file=internal-api/server.py -o yaml --dry-run=client | kubectl apply -f -
kubectl -n lab-gateway get secret gateway-key >/dev/null 2>&1 || kubectl -n lab-gateway create secret generic gateway-key --from-file=key=/dev/stdin
kubectl apply -f k8s/20-internal-api.yaml -f k8s/10-gateway.yaml -f k8s/70-validator.yaml
kubectl -n lab-internal rollout status deploy/billing-internal --timeout=180s
kubectl -n lab-gateway  rollout status deploy/gateway --timeout=180s
# every image a pod uses is on the node before any measurement, by digest (perf.py starts pods with imagePullPolicy: Never)
# (a crictl pull leaves no kubelet pull record; the gateway's deployment, applied above, is the first kubelet pull of the
# python image and records it under the name "python", the name every manifest and perf.py use)
for img in docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b docker.io/curlimages/curl:8.11.1@sha256:c1fe1679c34d9784c1b0d1e5f62ac0a79fca01fb6377cdd33e90473c6f9f9a69; do sudo k3s crictl pull "$img"; done
bash infra/build-images.sh
