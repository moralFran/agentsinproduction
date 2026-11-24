#!/usr/bin/env bash
# Runs ON aip-ctx-01, after install-k3s-kata.sh (added 2026-11-15, experiment 05). With virtiofs, Kata backs every guest's
# RAM with a file in /dev/shm, which Ubuntu sizes at half of the host's memory (16G on n2-standard-8). Guests do not give
# memory back, so a few pods with large limits fill it and a QEMU process dies ("Unexpected end-of-file before all data
# were read"; the pod fails with an empty log). This raises /dev/shm to 28G of the 32G; the harness keeps the sum of
# (memory limit + 2 GiB) of running pods under 26 GiB (cases/team_host.py, cpu_slots). Not persistent across a reboot:
# run it again after one.
#
# Node name (added 2026-11-16, after the resize to 32 vCPUs). After a stop/start k3s came up before the VM had its full
# host name and registered a second node under the short name; the gateway's volume is bound to the first name, so the
# gateway did not start. The name is pinned in /etc/rancher/k3s/config.yaml; if a node with another name is registered,
# restart k3s and delete that node (kubectl delete node <short name>). The budget state on the volume was not touched.
set -euo pipefail
sudo mount -o remount,size="${SHM_SIZE:-28G}" /dev/shm
df -h /dev/shm | tail -1
if [ ! -s /etc/rancher/k3s/config.yaml ]; then
  sudo mkdir -p /etc/rancher/k3s; echo "node-name: $(hostname -f)" | sudo tee /etc/rancher/k3s/config.yaml
fi
