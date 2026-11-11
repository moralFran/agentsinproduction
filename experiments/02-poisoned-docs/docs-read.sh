#!/usr/bin/env bash
# Pages the agent opened for one run of one question.   Usage: ./docs-read.sh results/p2-B.jsonl q39 3
jq -r --arg q "$2" --argjson r "${3:-1}" 'select(.qid == $q and .run == $r) | "\(.qid) run\(.run) opened: \(.docs_read | join(", "))"' "${1:?results.jsonl}" | fold -s -w 76
