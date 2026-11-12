#!/usr/bin/env bash
# Follow-up integration check (2026-11-12), runs ON the VM in the fresh run folder. Exercises the eligibility gate of
# cases/freeze.py. The decisions written here are THROWAWAY ("integration check, not a real eligibility decision"):
# they are not Francisco's decisions and exist only in the fresh run folder of this check.
#   1. freeze.py with the empty decisions file: expected to stop at the first case that needs a decision;
#   2. a decision with a STALE digest for that case: must be refused;
#   3. decisions with the right digest, one message at a time ("exclude" for nkanaev/yarr, "include" for every other
#      case the gate names), until freeze.py freezes the list or stops for another reason.
# usage: freeze-gate-check.sh <run-dir> <out-dir>
set -uo pipefail
cd "$1"; out="$2"; mkdir -p "$out"; D=cases/eligibility-decisions.json
[ -e ARCHIVE ] && { echo "refusing: archive folder"; exit 1; }
{
echo "== $(date -u +%FT%TZ) decisions file at the start: $(cat "$D")"
for step in $(seq 1 14); do
  msg=$(python3 cases/freeze.py 2>&1); rc=$?
  echo "-- freeze.py run $step: exit status $rc"; echo "$msg"
  [ $rc = 0 ] && break
  cid=$(printf '%s' "$msg" | sed -n 's/^case \([^ ]*\) needs an eligibility decision.*/\1/p'); digest=$(printf '%s' "$msg" | sed -n 's/.*repro_sha256=\([0-9a-f]\{64\}\).*/\1/p')
  [ -n "$cid" ] && [ -n "$digest" ] || { echo "freeze.py stopped for another reason; not continuing"; break; }
  if [ "$step" = 1 ]; then use=$(printf '%064d' 0); note="STALE digest on purpose"; else use="$digest"; note="digest from the message"; fi
  decision=include; case "$cid" in nkanaev-yarr-*) decision=exclude;; esac
  python3 - "$D" "$cid" "$decision" "$use" <<'PY'
import json, sys
path, cid, decision, digest = sys.argv[1:]
d = json.load(open(path)); d[cid] = {"decision": decision, "reason": "throwaway entry written by the integration check to exercise the gate", "reviewer": "integration check, not a real eligibility decision", "repro_sha256": digest}
json.dump(d, open(path, "w"), indent=2)
PY
  echo "   wrote decision for $cid: $decision ($note)"
done
echo "== decisions file at the end"; cat "$D"; echo
echo "== cases/eligibility-at-freeze.json"; cat cases/eligibility-at-freeze.json 2>/dev/null; echo
echo "== cases.csv ($(sha256sum cases/cases.csv 2>/dev/null | cut -c1-64))"; cut -d, -f1,10 cases/cases.csv 2>/dev/null
echo "== not-reproduced.csv"; cat cases/not-reproduced.csv 2>/dev/null; echo "== intermittent.csv"; cat cases/intermittent.csv 2>/dev/null
echo "== freeze.py again (the list is frozen once)"; python3 cases/freeze.py; echo "exit status $?"
} > "$out/freeze-gate-check.log" 2>&1
cp "$D" cases/eligibility-at-freeze.json cases/cases.csv cases/not-reproduced.csv cases/intermittent.csv "$out/" 2>/dev/null
