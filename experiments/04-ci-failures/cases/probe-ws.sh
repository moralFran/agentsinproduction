#!/usr/bin/env bash
# Runs ON aip-ci-01. The second reviewer's three probe tests for gobwas/ws (wsflate), run in an executor pod (Kata, no
# network) on one tree: "broken", "fixed" (the maintainer's fix) or an agent attempt's run id.  usage: probe-ws.sh <label>
cd "$(dirname "$0")/.." && KUBECONFIG=~/.kube/config python3 cases/audit.py ws "$1"
