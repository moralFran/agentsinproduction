#!/usr/bin/env bash
# Runs ON aip-endpoint-01, from the folder that holds server.py. Starts the test endpoint as a transient systemd unit.
# systemd-run starts in /, so the script is given by absolute path and the unit gets an explicit working directory.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; srv="$here/server.py"; [ -f "$srv" ] || srv="$here/../endpoint/server.py"
srv="$(realpath "$srv")"
sudo systemctl stop aip-endpoint 2>/dev/null || true
sudo systemd-run --unit=aip-endpoint --working-directory="$(dirname "$srv")" \
  -p StandardOutput=append:/var/log/aip-endpoint.log -p StandardError=append:/var/log/aip-endpoint.log python3 -u "$srv" 8080
sleep 1; curl -s -m 3 -o /dev/null -w 'self-test: HTTP %{http_code}\n' http://127.0.0.1:8080/self-test
