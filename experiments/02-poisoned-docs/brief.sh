#!/usr/bin/env bash
# Every run of one question: PASS/FAIL and the sentence of the answer that states the price (markdown stripped).
# Usage: ./brief.sh results/p1-A.jsonl q41
jq -r --arg q "$2" 'select(.qid == $q) | "run\(.run)  \(if .passed then "PASS" else "FAIL" end)  \(.answer | gsub("\\*\\*"; "") | [splits("(?<=\\.)\\s*")] | (map(select(test("\\$"))) | first) // .[0])"' "${1:?results.jsonl}" | fold -s -w 76
