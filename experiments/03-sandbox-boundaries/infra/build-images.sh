#!/usr/bin/env bash
# Runs ON aip-kata-01. Builds the two images with Docker and imports them into k3s's containerd (no registry).
# Docker is stopped again afterwards so it is not running during measurements.
# Tag 4: the agent and the validator of the fourth review (tags 1-3 are the images of the 2026-11-11 run).
set -euo pipefail
command -v docker >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq docker.io >/dev/null; }
sudo systemctl start docker
sudo docker build -q -t aip-agent:4 -f agent/Dockerfile . && sudo docker build -q -t aip-validator:4 -f validator/Dockerfile .
sudo docker save aip-agent:4 aip-validator:4 | sudo k3s ctr images import - | tail -2
sudo docker image inspect aip-agent:4 aip-validator:4 --format '{{.RepoTags}} {{.Id}}'
sudo systemctl stop docker docker.socket
