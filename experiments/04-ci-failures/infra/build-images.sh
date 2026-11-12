#!/usr/bin/env bash
# Runs ON aip-ci-01. Builds the box image with Docker and imports it into k3s's containerd (no registry).
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Docker is not installed: run infra/install-docker.sh first" >&2; exit 1; }   # check added 2026-11-12
sudo docker build -q -t aip-ci-box:1 -f Dockerfile.box . 
sudo docker save aip-ci-box:1 | sudo k3s ctr images import - | tail -1
sudo docker run --rm aip-ci-box:1 sh -c 'go version; python3 --version; /opt/agent-venv/bin/python -c "import anthropic; print(\"anthropic\", anthropic.__version__)"; uv --version; git --version'
