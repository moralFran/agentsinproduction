#!/usr/bin/env bash
# Runs ON aip-ctx-01. criteria E22: every saved patch of a round is validated again with the stricter reading (a required
# case passes only if its file ended clean) and with the whole result of every sample kept in /srv/ci/keep. No model
# call, no agent: only cases/validate.py on results/patches/<round>/<run>.diff. Nothing is overwritten: the controls go
# to /srv/ci/validate/E22, the attempts' verdicts to results/revalidate-<round>/<run>.verdict.json.
#   revalidate_team.sh <round> controls [P=4]   the 16 controls (gold and empty of T1..T8), P tasks at a time
#   revalidate_team.sh <round> attempts [P=4]   the round's patches, P at a time; REFUSES to start unless the 16 redone
#                                               controls are there and right (gold resolved, empty not_resolved on F2P)
#   revalidate_team.sh <round> compare          old and new outcome per attempt, from the two sets of files
# Resumable: a control or an attempt whose new verdict file exists is skipped.
set -uo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
round="${1:?round id}"; phase="${2:?controls|attempts|compare}"; P="${3:-4}"
CD=/srv/ci/validate/E22; RD="results/revalidate-$round"; mkdir -p "$CD" "$RD" /srv/ci/keep
controls_ok() {
  python3 - "$CD" <<'PY'
import json, os, sys
d = sys.argv[1]; bad = []
for n in range(1, 9):
    for kind, want in (("gold", "resolved"), ("empty", "not_resolved")):
        p = f"{d}/T{n}-{kind}.json"
        if not os.path.exists(p): bad.append(f"T{n}-{kind}: missing"); continue
        v = json.load(open(p))
        if v.get("outcome") != want or (kind == "empty" and not v.get("f2p_failed")): bad.append(f"T{n}-{kind}: {v.get('outcome')} {str(v.get('why', ''))[:120]}")
        elif "E22" not in v.get("rule", ""): bad.append(f"T{n}-{kind}: verdict written by the old rule")
print("CONTROLS E22:", "all 16 as expected" if not bad else f"{len(bad)} NOT as expected: {bad}")
sys.exit(1 if bad else 0)
PY
}
case "$phase" in
  controls)
    for n in 1 2 3 4 5 6 7 8; do for k in gold empty; do [ -s "$CD/T$n-$k.json" ] || echo "T$n $k"; done; done |
      xargs -P "$P" -L 1 bash -c 'CONTROL_DIR="$0" CONTROL_TAG=22 bash cases/controls.sh "$1" 4 "$2" 2>&1 | grep "^CONTROL" || echo "CONTROL $1 $2: no verdict line"' "$CD" || true   # $0 = dir, then the line: task, kind
    controls_ok;;
  attempts)
    controls_ok || { echo "the redone controls are not all as expected: the attempts are not touched (criteria E22)" >&2; exit 1; }
    python3 -c '
import json, sys
for l in open(f"results/attempts-{sys.argv[1]}.jsonl"):
    r = json.loads(l); print(r["case"], r["run"])' "$round" |
      while read -r cid run; do [ -s "$RD/$run.verdict.json" ] || echo "$cid $run"; done |
      xargs -P "$P" -L 1 bash -c 'python3 cases/validate.py "$2" "results/patches/$0/$3.diff" --prefix "vr-$3" --parallel "${VALIDATE_PARALLEL:-4}" --save "$1/$3.verdict.json" > "/tmp/reval-$3.exec" 2>&1; echo "REVALIDATED $3 $(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(\"outcome\"))" "$1/$3.verdict.json" 2>/dev/null || echo no-verdict-file)"' "$round" "$RD" || true   # $0 = round, $1 = dir, then the line: task, run
    bash "$0" "$round" compare;;
  compare)
    python3 - "$round" "$RD" <<'PY'
import json, os, sys
rnd, rd = sys.argv[1], sys.argv[2]; same = changed = missing = 0; lines = []
for l in open(f"results/attempts-{rnd}.jsonl"):
    r = json.loads(l); old = r["validator"]; p = f"{rd}/{r['run']}.verdict.json"
    if not os.path.exists(p): missing += 1; lines.append(f"  {r['run']}: old {old['outcome']} | new MISSING"); continue
    v = json.load(open(p)); dirty = sum(s.get("dirty_files", 0) for s in v.get("samples", [])); hit = sum(len(s.get("dirty_files_with_required_cases") or {}) for s in v.get("samples", []))
    tag = "same" if v.get("outcome") == old["outcome"] else "CHANGED"
    same += tag == "same"; changed += tag != "same"
    lines.append(f"  {r['run']}: old {old['outcome']} (stage {old.get('decided_in_stage')}) | new {v.get('outcome')} (stage {v.get('decided_in_stage')}) {tag} | samples {len(v.get('samples', []))}, dirty files {dirty}, with required cases {hit}, "
                 f"broken {len(v.get('broken', []))}, unstable {len(v.get('unstable_in_attempt', []))}, environment-dependent {len(v.get('environment_dependent', []))} {str(v.get('why', ''))[:160]}")
print(f"REVALIDATION {rnd}: {same} same, {changed} changed, {missing} missing"); print("\n".join(lines))
PY
    ;;
  *) echo "unknown phase $phase" >&2; exit 2;;
esac
