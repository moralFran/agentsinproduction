#!/usr/bin/env bash
# Run one eval configuration with the API key read from the macOS keychain (never written to disk).
# Usage: ./run.sh A [runs] [workers]
set -euo pipefail
cd "$(dirname "$0")"
cfg="${1:?config A|B|C}"; runs="${2:-3}"; workers="${3:-4}"; questions="${4:-questions.jsonl}"; out="${5:-results/$cfg.jsonl}"
export ANTHROPIC_API_KEY="$(security find-generic-password -a ANTHROPIC_API_KEY -w)"
./agent-eval-go -config "$cfg" -runs "$runs" -workers "$workers" -out "$out" -questions "$questions"
