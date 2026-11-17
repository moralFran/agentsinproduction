#!/usr/bin/env bash
# Runs ON aip-ci-01. Builds the box image with Docker and imports it into k3s's containerd (no registry).
# The Ubuntu base is pinned by digest: UBUNTU_DIGEST=sha256:... or, when unset, the digest of ubuntu:24.04 pulled now
# (printed and written to infra/versions.txt by the caller). Prints every tool version from inside the image.
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Docker is not installed: run infra/install-docker.sh first" >&2; exit 1; }
IMAGE="${BOX_IMAGE:-aip-team-box:1}"
if [ -z "${UBUNTU_DIGEST:-}" ]; then
  sudo docker pull -q ubuntu:24.04 >/dev/null
  UBUNTU_DIGEST=$(sudo docker inspect --format '{{index .RepoDigests 0}}' ubuntu:24.04 | sed 's/.*@//')
fi
echo "base: ubuntu:24.04@$UBUNTU_DIGEST"
sed "s/sha256:__UBUNTU_DIGEST__/$UBUNTU_DIGEST/" Dockerfile.box > /tmp/Dockerfile.box.resolved
sudo docker build -t "$IMAGE" -f /tmp/Dockerfile.box.resolved . 
sudo docker save "$IMAGE" | sudo k3s ctr images import - | tail -1
echo "image id: $(sudo docker inspect --format '{{.Id}}' "$IMAGE")"
echo "containerd: $(sudo k3s ctr images ls | grep "${IMAGE%%:*}" | awk '{print $1, $3}')"
sudo docker run --rm --network none "$IMAGE" sh -c '
  . /etc/os-release; echo "os: $PRETTY_NAME"; id
  flutter --version --suppress-analytics 2>&1 | head -4; dart --version 2>&1
  echo "node $(node --version)  npm $(npm --version)"; java -version 2>&1 | head -2
  echo "firebase-tools $(firebase --version)"; ls -1 "$FIREBASE_EMULATORS_PATH"
  /opt/agent-venv/bin/python -c "import anthropic, sys; print(\"python\", sys.version.split()[0], \"anthropic\", anthropic.__version__)"
  git --version; rsync --version | head -1
  ls /opt/flutter/bin/cache/artifacts/engine/linux-x64/ | head; du -sh /opt/flutter 2>/dev/null'
