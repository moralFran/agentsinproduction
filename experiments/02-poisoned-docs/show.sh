#!/usr/bin/env bash
# Print one answer next to what the grader expected (markdown bold stripped, wrapped at word boundaries).
# Usage: ./show.sh results/rec-C.jsonl q52 [run]
f="${1:?results.jsonl}"; q="${2:?qid}"; r="${3:-1}"
jq -r --arg q "$q" --argjson r "$r" 'select((.qid // .id) == $q and .run == $r) | "question: \(.question)\nanswer:   \(.answer | gsub("\\*\\*"; ""))\nexpected: \(.expected)\npassed:   \(.passed)"' "$f" | fold -s -w 76 | sed "/^$/d"
