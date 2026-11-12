#!/usr/bin/env bash
# Runs ON aip-kata-01. Installs pinned k3s, Helm and Kata Containers (kata-deploy chart). These are the versions of
# the recorded run (results/versions.txt). The admin kubeconfig is readable by root only; the lab user gets a 0600 copy.
#
# What is pinned, and how (fourth review):
#   - the two installer SCRIPTS: fetched at a fixed commit of their repository and checked against a SHA-256 computed
#     on 2026-11-12 from that commit (the commit each version tag pointed to that day). A different file stops here.
#   - k3s, Helm, Kata: by version. The k3s and Helm installers download the release they are told to and check it
#     against the checksum file published next to it, which is the same origin, not an independent pin.
#   - the kata-deploy chart: by version tag. Its registry digest on 2026-11-12 is printed next to the one pulled, for
#     the record; a difference is reported, not enforced (helm's handling of a digest reference was not tried here).
# Not pinned: the images kata-deploy itself pulls, the Ubuntu image (an image family in infra/create.sh, so the host
# kernel can differ from the recorded run), apt packages (docker.io, git), and the dependencies pip resolves for
# anthropic and pytest in the two Dockerfiles (those two are pinned by version, not by hash).
set -euo pipefail
K3S_VERSION="${K3S_VERSION:-v1.37.2+k3s1}"; KATA_VERSION="${KATA_VERSION:-4.3.1}"; HELM_VERSION="${HELM_VERSION:-v3.22.1}"
K3S_INSTALLER="https://raw.githubusercontent.com/k3s-io/k3s/f6973cb850e9b245585363d15bde80904ac862fd/install.sh"            # tag v1.37.2+k3s1
K3S_INSTALLER_SHA256="ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b"
HELM_INSTALLER="https://raw.githubusercontent.com/helm/helm/d6c1a0e4027caa6abc7892e7ea9f0cda7447baa3/scripts/get-helm-3"   # tag v3.22.1
HELM_INSTALLER_SHA256="e4a604efcff328eef2b2c7e67445d609f333e3875b34420ebf4e5ae379d259bb"
KATA_CHART="oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy"
KATA_CHART_DIGEST="sha256:8eab352a59b42dc7b3aebe87d4114b936a8576967d4800047ce708fcebb61d2e"                               # of version 4.3.1
fetch() {   # <url> <sha256> -> path of the downloaded file, only if it has that checksum
  local f; f="$(mktemp)"
  curl -fsSL "$1" -o "$f"
  echo "$2  $f" | sha256sum -c --quiet - >&2 || { echo "checksum mismatch: $1" >&2; return 1; }
  echo "$f"
}
k3s_installer="$(fetch "$K3S_INSTALLER" "$K3S_INSTALLER_SHA256")"
sudo INSTALL_K3S_VERSION="$K3S_VERSION" sh "$k3s_installer" --write-kubeconfig-mode 600
mkdir -p ~/.kube && sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config && chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
until kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 3; done
helm_installer="$(fetch "$HELM_INSTALLER" "$HELM_INSTALLER_SHA256")"
sudo DESIRED_VERSION="$HELM_VERSION" bash "$helm_installer" >/dev/null
pulled="$(helm pull "$KATA_CHART" --version "$KATA_VERSION" --destination "$(mktemp -d)" 2>&1 | awk '/^Digest:/ {print $2}' || true)"
echo "kata-deploy chart $KATA_VERSION digest: ${pulled:-not reported by helm} (on 2026-11-12: $KATA_CHART_DIGEST)"
[ -z "$pulled" ] || [ "$pulled" = "$KATA_CHART_DIGEST" ] || echo "NOTE: the chart digest differs from the one recorded on 2026-11-12"
helm install kata-deploy "$KATA_CHART" --version "$KATA_VERSION" \
  --namespace kube-system --set k8sDistribution=k3s --wait --timeout 10m
echo "k3s: $(k3s --version | head -1)"; echo "kata: $KATA_VERSION"; kubectl get runtimeclass | grep kata-qemu
