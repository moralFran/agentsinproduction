#!/usr/bin/env bash
# Runs ON aip-ci-01, from the experiment folder, after install-k3s-kata.sh and build-images.sh. Namespaces, policies,
# the gateway (provider key read from STDIN straight into a Secret, never into a file), the code ConfigMap, /srv/ci.
# usage: <key on stdin> | infra/setup-lab.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config
sudo mkdir -p /srv/ci/cases /srv/ci/secret /srv/ci/work /srv/ci/uv /srv/ci/logs && sudo chown -R "$USER" /srv/ci
kubectl apply -f k8s/00-base.yaml
kubectl -n ci-gateway create configmap gateway-code --from-file=gateway/gateway.py -o yaml --dry-run=client | kubectl apply -f -
kubectl -n ci-gateway get secret gateway-key >/dev/null 2>&1 || kubectl -n ci-gateway create secret generic gateway-key --from-file=key=/dev/stdin
# Separate runner credential; never mounted into case pods or sent to the model.
(umask 077; [ -s /srv/ci/admin-key ] || python3 -c 'import secrets; print(secrets.token_hex(32))' > /srv/ci/admin-key)
chmod 600 /srv/ci/admin-key
kubectl -n ci-gateway create secret generic gateway-admin-key --from-file=key=/srv/ci/admin-key -o yaml --dry-run=client | kubectl apply -f -
kubectl apply -f k8s/10-gateway.yaml
# ConfigMap updates do not reload an already-running Python process. Wait for a new gateway pod before continuing.
kubectl -n ci-gateway rollout restart deploy/gateway
kubectl -n ci-gateway rollout status deploy/gateway --timeout=180s
infra/code-configmap.sh
for img in docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b; do sudo k3s crictl pull "$img" >/dev/null; done
