#!/usr/bin/env bash
# Ask the agent one question and watch the tool calls (key from the keychain, never on disk).
# Usage: ./ask.sh "question" [A|B|C] [-corpus DIR] [-index FILE]
set -euo pipefail
cd "$(dirname "$0")"
q="${1:?question}"; cfg="${2:-A}"; shift $(( $# > 2 ? 2 : $# ))
export ANTHROPIC_API_KEY="$(security find-generic-password -a ANTHROPIC_API_KEY -w)"
./agent-eval-go -config "$cfg" -ask "$q" "$@"
