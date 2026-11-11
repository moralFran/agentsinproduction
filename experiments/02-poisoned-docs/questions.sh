#!/usr/bin/env bash
# First N eval questions with the string the grader expects.   Usage: ./questions.sh 3
head -n "${1:-3}" "$(dirname "$0")/questions.jsonl" | jq -r '"\(.id)  \(.question)\n     expects: \(.expected_contains)"' | fold -s -w 76
