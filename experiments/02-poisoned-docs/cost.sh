#!/usr/bin/env bash
# Runs and total API cost of the original experiment.   Usage: ./cost.sh results/A.jsonl results/B.jsonl results/C.jsonl
jq -s '{runs: length, total_usd: (map(.cost_usd) | add * 100 | round / 100)}' "$@"
