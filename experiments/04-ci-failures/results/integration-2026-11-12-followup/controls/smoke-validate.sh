#!/usr/bin/env bash
# Follow-up integration (2026-11-12), runs ON the VM. Smoke: cases/validate.py on one archived patch per smoke case.
# usage: smoke-validate.sh <archive-dir> <run-dir> <out-dir>
cd "$2"; out="$3"; mkdir -p "$out"; P="$1/results/patches"
v() { python3 cases/validate.py "$1" "$2" "sv-$3" > "$out/$3.out" 2>&1; echo "$3 ($1, $(basename "$2")): $(grep '^EXECUTOR ' "$out/$3.out" | python3 -c 'import json,sys; r=json.loads(sys.stdin.read()[9:]); print(r.get("outcome"), "suite", r.get("suite_pass"), "hidden", r.get("hidden_pass"), r.get("why", ""))')"; }
v gobwas-ws-a567dfd6 "$P/v2/v2-e88f0806-r2.diff" go-green-passes-hidden &
v gobwas-ws-a567dfd6 "$P/v1/v1-e88f0806-r1.diff" go-green-fails-hidden &
v rmax-scrapy-redis-8d8672f2 "$P/v1/v1-1206f641-r3.diff" py-still-red &
v openbyteinc-quantdinger-733f7bc7 "$P/v1/v1-a352a7c0-r3.diff" py-green-fails-hidden &
wait; echo SMOKE_VALIDATE_DONE
