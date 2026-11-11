#!/usr/bin/env bash
# All answers to one question in one file (every run).   Usage: ./answers.sh results/rec-A.jsonl q52
jq -r --arg q "$2" 'select(.qid == $q) | "run\(.run)  \(if .passed then "PASS" else "FAIL" end)  \(.answer)"' "${1:?results.jsonl}"
