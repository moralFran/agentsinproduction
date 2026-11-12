#!/usr/bin/env bash
# Runs ON aip-ci-01, after create.sh and before build-images.sh. Added 2026-11-12, after the collection: the recorded run
# had Docker installed by hand on the VM and its version was not recorded; this script makes that step explicit.
#  - installs Ubuntu's docker.io package; DOCKER_IO_VERSION=<apt version> pins it (list them with
#    `apt-cache madison docker.io`); without it, the version the image's archive has that day is installed and printed;
#  - enables and starts the daemon;
#  - installs host Git/rsync for the trusted preparation controller. Repository builds now run in Kata pods;
#    Docker is used only to build/export the lab image, via sudo in infra/build-images.sh.
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq git rsync >/dev/null
if [ -n "${DOCKER_IO_VERSION:-}" ]; then sudo apt-get install -y -qq "docker.io=$DOCKER_IO_VERSION" >/dev/null
else sudo apt-get install -y -qq docker.io >/dev/null; fi
sudo systemctl enable --now docker
echo "docker.io $(dpkg-query -W -f='${Version}' docker.io), git and rsync installed"
