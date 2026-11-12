#!/usr/bin/env bash
# Runs ON aip-ci-01. Reproduction of one prepared case (criteria.md §12): N runs on the broken tree, N on the
# maintainer's fix, each tree in its own executor pod (Kata, no network). Appends one JSON line to cases/repro.jsonl (or $REPRO_OUT).
set -euo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
[ -z "${REPRO_OUT:-}" ] && [ -e ARCHIVE ] && [ "${ALLOW_ARCHIVE_WRITE:-0}" != 1 ] && { echo "this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1" >&2; exit 1; }   # added 2026-11-12, after the collection
cid="${1:?case id}"; n="${2:-3}"; t=$(mktemp -d)
python3 cases/pod.py exec "$cid" "rb-$cid" 2400 -- python3 -u /code/executor.py repro broken "$n" | grep '^EXECUTOR ' | sed 's/^EXECUTOR //' > "$t/b" || true
python3 cases/pod.py exec "$cid" "rf-$cid" 2400 -- python3 -u /code/executor.py repro fixed "$n" | grep '^EXECUTOR ' | sed 's/^EXECUTOR //' > "$t/f" || true
python3 cases/pod.py exec "$cid" "rh-$cid" 2400 -- python3 -u /code/executor.py repro hidden-broken "$n" | grep '^EXECUTOR ' | sed 's/^EXECUTOR //' > "$t/h" || true
python3 - "$cid" "$t/b" "$t/f" "$n" "$t/h" >> ${REPRO_OUT:-cases/repro.jsonl} <<'PY'
import json, sys
cid, n = sys.argv[1], int(sys.argv[4])
rd = lambda p: (json.loads(open(p).read() or "{}"))
b, f, h = rd(sys.argv[2]), rd(sys.argv[3]), rd(sys.argv[5])
bf, fp = b.get("fail"), f.get("pass")
if bf is None or fp is None: v = "infra_error"
elif bf == n and fp == n: v = "reproduced"
elif bf == 0 and fp == n: v = "not_reproduced_broken_passes"
elif fp == 0 and bf == n: v = "not_reproduced_fix_fails"
else: v = "intermittent"
hidden_fixed = f.get("hidden_runs", [])
hidden_broken = h.get("runs", [])
if v == "reproduced" and not h.get("not_applicable"):
    if len(hidden_fixed) != n or len(hidden_broken) != n or any(r.get("rc") in (None, 124) for r in hidden_fixed + hidden_broken):
        v = "infra_error"
    elif 0 < sum(r.get("rc") == 0 for r in hidden_broken) < n:
        v = "intermittent"
if v == "reproduced" and hidden_fixed and any(r.get("rc") != 0 for r in hidden_fixed):
    v = "intermittent" if any(r.get("rc") == 0 for r in hidden_fixed) else "not_reproduced_hidden_fix_fails"
hidden_control = {"broken_plus_tests": h.get("runs", []), "fixed": hidden_fixed,
                  "discriminates": bool(hidden_fixed) and len(hidden_fixed) == n and len(h.get("runs", [])) == n and
                                   all(r.get("rc") == 0 for r in hidden_fixed) and all(r.get("rc") not in (None, 0, 124) for r in h["runs"])}
integrity_control = {"suite": [s.get("integrity", {}) for s in f.get("runs", [])],
                     "hidden": [s.get("integrity", {}) for s in hidden_fixed]}
checks = integrity_control["suite"] + integrity_control["hidden"]
complete = len(integrity_control["suite"]) == n and (h.get("not_applicable") or len(integrity_control["hidden"]) == n)
if not complete or any(c.get("outcome") not in ("sampled", "rejected_by_validator") for c in checks):
    integrity_control["outcome"] = "error"
elif any(c["outcome"] == "rejected_by_validator" for c in checks):
    integrity_control["outcome"] = "changed"
else:
    integrity_control["outcome"] = "clean"
if integrity_control["outcome"] == "error":
    v = "infra_error"
elif v == "reproduced" and integrity_control["outcome"] == "changed":
    v = "incompatible_test_side_effects"
print(json.dumps({"id": cid, "hidden_control": hidden_control, "integrity_control": integrity_control, "verdict": v, "broken_fail": bf, "fixed_pass": fp, "n": n,
                  "hidden_on_fix_rc": (f.get("hidden_runs") or [{}])[0].get("rc"), "broken": b, "fixed": f}))
PY
rm -rf "$t"
tail -1 ${REPRO_OUT:-cases/repro.jsonl} | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["id"], r["verdict"], "| broken failed", r["broken_fail"], "of", r["n"], "| fixed passed", r["fixed_pass"], "of", r["n"], "| hidden on fix rc", r["hidden_on_fix_rc"])'
