#!/usr/bin/env bash
# Runs ON aip-kata-01, with the RBAC lab applied (k8s/50-rbac-lab.yaml) and rbac-probe.sh copied to /tmp/p.sh in both
# pods. One pass of the fixed reads per identity, each with the pod's own token; real API answers.
set -euo pipefail
export KUBECONFIG=~/.kube/config
for id in reader noaccess; do kubectl -n lab-rbac exec "id-$id" -- sh /tmp/p.sh "$id" 1; done \
  | python3 "$(dirname "$0")/tally-rbac.py" /dev/stdin
