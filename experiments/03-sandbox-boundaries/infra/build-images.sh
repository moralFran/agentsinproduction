#!/usr/bin/env bash
# Runs ON aip-kata-01. Builds the two images with Docker and imports them into k3s's containerd (no registry).
# Docker is stopped again afterwards so it is not running during measurements.
set -euo pipefail
command -v docker >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq docker.io >/dev/null; }
sudo systemctl start docker
sudo docker build -q -t aip-agent:3 -f agent/Dockerfile . && sudo docker build -q -t aip-validator:3 -f validator/Dockerfile .
sudo docker save aip-agent:3 aip-validator:3 | sudo k3s ctr images import - | tail -2
sudo docker image inspect aip-agent:3 aip-validator:3 --format '{{.RepoTags}} {{.Id}}'
sudo systemctl stop docker docker.socket
