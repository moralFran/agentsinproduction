#!/usr/bin/env bash
# The 7 price-dependent questions under the planted page: grader verdict of each run, both models (grader v2).
cd "$(dirname "$0")"
printf "%-5s %-20s %s\n" "" "Sonnet  run1 2 3" "Haiku  run1 2 3"
for q in q02 q04 q05 q41 q44 q45 q46; do
  a=$(jq -r --arg q $q 'select(.qid==$q) | if .passed then "PASS" else "FAIL" end' results/p1-A.jsonl | paste -sd' ' -)
  b=$(jq -r --arg q $q 'select(.qid==$q) | if .passed then "PASS" else "FAIL" end' results/p1-B.jsonl | paste -sd' ' -)
  printf "%-5s %-20s %s\n" $q "$a" "$b"
done
printf "\nall 60 questions:  Sonnet %s/180   Haiku %s/180\n" "$(jq -s '[.[]|select(.passed)]|length' results/p1-A.jsonl)" "$(jq -s '[.[]|select(.passed)]|length' results/p1-B.jsonl)"
