#!/usr/bin/env bash
# Runs ON aip-ci-01. The two validator controls of a task (after `team_host.py derive <T#>`):
#   gold   the owner's fix (source files only, as an agent patch would carry it) must come out `resolved` (stage 2);
#   empty  an empty patch must come out `not_resolved`, failing on F2P in stage 1.
# Both follow criteria E10 (two stages), like any attempt.
# Verdicts are saved in /srv/ci/validate/<T#>-{gold,empty}.json. usage: controls.sh <T#> [parallel] [gold|empty|both]
# CONTROL_DIR=<dir> saves them elsewhere (criteria E22: the controls redone with the stricter reading go to
# /srv/ci/validate/E22 and the earlier ones are not overwritten); CONTROL_TAG is appended to the pod-name prefix.
set -uo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
t="$1"; p="${2:-2}"; which="${3:-both}"; d="${CONTROL_DIR:-/srv/ci/validate}"; tag="${CONTROL_TAG:-}"; mkdir -p /srv/ci/validate "$d"; : > /srv/ci/validate/empty.diff
if [ "$which" != empty ]; then
  python3 cases/validate.py "$t" "/srv/ci/secret/$t/fix-source.diff" --prefix "vg$tag" --parallel "$p" --save "$d/$t-gold.json" | grep '^VERDICT' | cut -c1-400
fi
if [ "$which" != gold ]; then
  python3 cases/validate.py "$t" /srv/ci/validate/empty.diff --prefix "ve$tag" --parallel "$p" --save "$d/$t-empty.json" | grep '^VERDICT' | cut -c1-400
fi
python3 - "$t" "$which" "$d" <<'PY'
import json, os, sys
t, which, d = sys.argv[1], sys.argv[2], sys.argv[3]
for kind, want in (("gold", "resolved"), ("empty", "not_resolved")):
    if which not in (kind, "both") or not os.path.exists(f"{d}/{t}-{kind}.json"): continue
    v = json.load(open(f"{d}/{t}-{kind}.json"))
    ok = v.get("outcome") == want and (kind == "gold" or v.get("f2p_failed", 0) > 0)
    s1, s2 = v.get("stage1") or {}, v.get("stage2") or {}
    print(f"CONTROL {t} {kind}: {v.get('outcome')} (expected {want}) decided in stage {v.get('decided_in_stage')} | stage 1: f2p_failed={v.get('f2p_failed')}/{v.get('f2p_total')} "
          f"p2p_failed={s1.get('p2p_failed')} wall={s1.get('wall_s')}s | stage 2: broken={len(v.get('broken', []))} unstable_in_attempt={len(v.get('unstable_in_attempt', []))} environment_dependent={len(v.get('environment_dependent', []))} "
          f"reruns={s2.get('rerun_samples')} wall={s2.get('wall_s')}s | pods={len(v.get('samples', []))} total wall={v.get('wall_s')}s {'OK' if ok else 'CONTROL FAILED'} {str(v.get('why', ''))[:200]}")
PY
