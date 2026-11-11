#!/usr/bin/env bash
# List the failed runs of a results file: question id, run, question.   Usage: ./failures.sh results/rec-C.jsonl
jq -r 'select(.passed == false) | "\(.qid)  run\(.run)  \(.question)"' "${1:?results.jsonl}" | sort
