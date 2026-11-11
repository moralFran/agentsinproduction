#!/usr/bin/env bash
# Re-score saved answers with the grader in questions.jsonl (v2). No API calls.
# Usage: ./regrade.sh [results/X.jsonl ...]   (default: the historical runs results/rec-A.jsonl, rec-B, rec-C)
# Each input FILE.jsonl is written to FILE.v2.jsonl.
set -euo pipefail
cd "$(dirname "$0")"
files=("$@"); [[ ${#files[@]} -eq 0 ]] && files=(results/rec-A.jsonl results/rec-B.jsonl results/rec-C.jsonl)
for f in "${files[@]}"; do ./agent-eval-go -regrade "$f" -questions questions.jsonl -out "${f%.jsonl}.v2.jsonl"; done
