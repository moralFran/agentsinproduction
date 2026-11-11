#!/usr/bin/env bash
# Runs ON aip-kata-01. One pass of HTTPS to a public site from the diagnostic pod, two ways, under whatever policy is
# applied right now: by name (needs DNS first), and with the address resolved on the node beforehand and pinned
# (`curl --resolve`: hostname and certificate check kept, no name lookup), so a failure cannot be a failed lookup.
set -euo pipefail
export KUBECONFIG=~/.kube/config
HOST=example.com; IP=$(getent ahostsv4 "$HOST" | awk 'NR==1{print $1}'); [ -n "$IP" ]
one() { kubectl -n lab-agent exec diag -- sh -c 'code=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$@" 2>/dev/null); rc=$?; case $rc in 0) echo "http_$code";; 28) echo timeout;; 7) echo conn_refused;; 6) echo dns_failure;; *) echo "curl_err_$rc";; esac' probe "$@"; }
printf '%-34s %s\n' "https://$HOST by name"   "$(one "https://$HOST/")"
printf '%-34s %s\n' "https://$HOST, IP pinned" "$(one --resolve "$HOST:443:$IP" "https://$HOST/")"
