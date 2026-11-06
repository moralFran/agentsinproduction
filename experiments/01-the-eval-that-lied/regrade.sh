#!/usr/bin/env bash
# Re-score the saved answers of A, B and C with the grader in questions.jsonl (v2). No API calls.
set -euo pipefail
cd "$(dirname "$0")"
for X in A B C; do ./agent-eval-go -regrade "results/rec-$X.jsonl" -questions questions.jsonl -out "results/rec-$X.v2.jsonl"; done
