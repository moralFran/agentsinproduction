#!/usr/bin/env bash
# Runs ON aip-ci-01, after create.sh and before build-images.sh. Added 2026-11-12, after the collection: the recorded run
# had Docker installed by hand on the VM and its version was not recorded; this script makes that step explicit.
#  - installs Ubuntu's docker.io package; DOCKER_IO_VERSION=<apt version> pins it (list them with
#    `apt-cache madison docker.io`); without it, the version the image's archive has that day is installed and printed;
#  - enables and starts the daemon;
#  - adds the VM user to the docker group, because cases/pipeline.sh runs `docker run` WITHOUT sudo (the preparation
#    container runs as the VM user's uid). The group only applies to a NEW login: log out and in again (or `newgrp docker`).
set -euo pipefail
sudo apt-get update -qq
if [ -n "${DOCKER_IO_VERSION:-}" ]; then sudo apt-get install -y -qq "docker.io=$DOCKER_IO_VERSION" >/dev/null
else sudo apt-get install -y -qq docker.io >/dev/null; fi
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
echo "docker.io $(dpkg-query -W -f='${Version}' docker.io) installed; $USER added to the docker group (log in again before cases/pipeline.sh)"
