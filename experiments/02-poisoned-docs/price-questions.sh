#!/usr/bin/env bash
# The 7 questions whose right answer the planted pricing page changes.
jq -r 'select(.id | IN("q02","q04","q05","q41","q44","q45","q46")) | .id + "  " + .question' "$(dirname "$0")/questions.jsonl" | fold -s -w 76
