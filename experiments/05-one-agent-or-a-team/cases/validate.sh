#!/usr/bin/env bash
# Runs ON aip-ci-01. Runs the validator (criteria E2 + E10, two stages) on a patch for a task and prints a short reading.
# usage: validate.sh <T#> <patch.diff> [validate.py options]
set -euo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
t="$1"; p="$2"; shift 2
python3 cases/validate.py "$t" "$p" --prefix "vc-$(echo "$t$p" | md5sum | cut -c1-8)" "$@" \
  | grep '^VERDICT ' | sed 's/^VERDICT //' | python3 -c 'import json,sys; r=json.load(sys.stdin); s1=r.get("stage1") or {}; s2=r.get("stage2") or {}; print("outcome:", r.get("outcome"), "| decided in stage", r.get("decided_in_stage")); print("why:", str(r.get("why", "-"))[:120]); print("stage 1: F2P failed", r.get("f2p_failed"), "of", r.get("f2p_total"), "| P2P of the commit files failed:", s1.get("p2p_failed"), "| wall", s1.get("wall_s"), "s"); print("stage 2: broken", len(r.get("broken", [])), "| unstable in attempt", len(r.get("unstable_in_attempt", [])), "| files rerun", sum(len(v) for v in (s2.get("files_rerun") or {}).values()), "| wall", s2.get("wall_s"), "s"); print("pods:", len(r.get("samples", [])), "| total wall:", r.get("wall_s"), "s")'
