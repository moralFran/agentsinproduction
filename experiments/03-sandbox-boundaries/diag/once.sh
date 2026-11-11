#!/usr/bin/env bash
# Runs ON aip-kata-01. One pass of the fixed network probes from the diagnostic pod, under whatever NetworkPolicy is
# applied right now; one readable line per probe. The probe paths carry the phase "once", so the endpoint and gateway
# logs of the 10x collection stay countable.   usage: once.sh [runtime-label]
set -euo pipefail
export KUBECONFIG=~/.kube/config; . "$(dirname "$0")/../lab.env"
kubectl -n lab-agent exec diag -- sh -c ': > /tmp/body; exec sh /tmp/net-probe.sh "$@"' probe once "${1:-kata-qemu}" 1 "$ENDPOINT_IP" "$NODE_IP" \
  | python3 -u "$(dirname "$0")/fmt-probe.py"
