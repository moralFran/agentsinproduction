#!/usr/bin/env bash
# Print one answer next to what the grader expected.   Usage: ./show.sh results/rec-C.jsonl q52 [run]
f="${1:?results.jsonl}"; q="${2:?qid}"; r="${3:-1}"
jq -r --arg q "$q" --argjson r "$r" 'select(.qid == $q and .run == $r) | "question: \(.question)\nanswer:   \(.answer)\nexpected: \(.expected)\npassed:   \(.passed)"' "$f"
