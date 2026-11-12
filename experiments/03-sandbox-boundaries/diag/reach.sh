#!/usr/bin/env bash
# Runs ON aip-kata-01. Runs diag/reach.py inside a pod made from the agent's image and spec (default: "inspect"),
# with the endpoint's address from lab.env.   usage: reach.sh [pod]
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . ./lab.env
# the script goes in as an argument: with stdin, kubectl exec can stop relaying output once stdin closes
kubectl -n lab-agent exec "${1:-inspect}" -- env ENDPOINT_IP="$ENDPOINT_IP" python3 -c "$(cat diag/reach.py)"
