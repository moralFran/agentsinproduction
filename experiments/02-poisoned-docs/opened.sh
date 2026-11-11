#!/usr/bin/env bash
# How many answers opened a given page (docs_read).   Usage: ./opened.sh 20-assistant-notes.md results/p3-*.jsonl
p="${1:?page}"; shift
for f in "$@"; do printf "%-24s %s / %s answers opened %s\n" "$f" "$(jq -s --arg p "$p" '[.[] | select(.docs_read // [] | index($p))] | length' "$f")" "$(jq -s length "$f")" "$p"; done
