#!/usr/bin/env bash
# Runs ON aip-ci-01. Installs pinned k3s, Helm and Kata Containers (kata-deploy chart). These are the versions of
# the recorded run (results/versions.txt). The admin kubeconfig is readable by root only; the lab user gets a 0600 copy.
set -euo pipefail
K3S_VERSION="${K3S_VERSION:-v1.37.2+k3s1}"; KATA_VERSION="${KATA_VERSION:-4.3.1}"; HELM_VERSION="${HELM_VERSION:-v3.22.1}"
curl -sfL https://get.k3s.io | sudo INSTALL_K3S_VERSION="$K3S_VERSION" sh -s - --write-kubeconfig-mode 600
mkdir -p ~/.kube && sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config && chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
until kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 3; done
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | sudo DESIRED_VERSION="$HELM_VERSION" bash >/dev/null
helm install kata-deploy oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy --version "$KATA_VERSION" \
  --namespace kube-system --set k8sDistribution=k3s --wait --timeout 10m
echo "k3s: $(k3s --version | head -1)"; echo "kata: $KATA_VERSION"; kubectl get runtimeclass | grep kata-qemu
