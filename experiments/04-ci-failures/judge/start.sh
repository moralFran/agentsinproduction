#!/usr/bin/env bash
# Starts the blind-judging page detached from the terminal (survives the session that started it).
# Usage: judge/start.sh [port=8791]      stop: pkill -f "judge/server.py"
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
port="${1:-8791}"
pkill -f "judge/server.py results/blind/packets" 2>/dev/null || true
nohup python3 -I judge/server.py results/blind/packets results/blind/verdicts.jsonl "$port" > /tmp/v5-judge.log 2>&1 < /dev/null &
disown
sleep 1
curl -s -o /dev/null -w "judge page: http://127.0.0.1:$port/ (HTTP %{http_code})\n" "http://127.0.0.1:$port/"
