#!/usr/bin/env bash
# Count failures per question id, per results file.   Usage: ./group.sh results/rec-{A,B,C}.jsonl
for f in "$@"; do echo "== $f"; jq -r 'select(.passed == false) | .qid' "$f" | sort | uniq -c; done
