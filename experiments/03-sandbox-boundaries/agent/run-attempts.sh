#!/usr/bin/env bash
# Runs ON aip-kata-01. N attempts per runtime, alternating, one fresh pod each, NetworkPolicy applied.
# Each patch is then checked in a fresh validator pod (other namespace, no network, pristine checkout).
# Every invocation is a ROUND with its own id: pod names, gateway run ids, patch paths and the output file all carry
# it, so a smoke test can never be confused with a collection.   usage: run-attempts.sh <N> <round-id>
#
# What comes from where in each row (fourth review):
#   measured here, outside the pod ... pod_phase, pod_wall_s (from the pod's creation to Succeeded or Failed)
#   decided by the validator ......... validation (from the patch text, in another pod)
#   reported by the pod itself ....... everything under "agent": outcome, calls, tokens, times, commands. The pod ran
#                                      model-chosen commands, so this is its account, not a measurement. The gateway's
#                                      log has the calls and tokens it saw for the run id (itself sent by the pod).
# The report is the last pod-log line `RESULT <nonce> <json>` with the nonce made here for that pod (agent/result.py);
# RESULT lines without it are counted in agent.report_lines_rejected. Needs only bash, kubectl and python3.
set -euo pipefail
export KUBECONFIG=~/.kube/config
cd "$(dirname "$0")/.."
N="${1:?attempts per runtime}"; ROUND="${2:?round id, e.g. main-20261111a}"
OUT="results/task-$ROUND.jsonl"; PDIR="results/patches/$ROUND"
[ ! -e "$OUT" ] && [ ! -e "$PDIR" ] || { echo "round $ROUND already exists; pick a new id"; exit 1; }
mkdir -p "$PDIR"; : > "$OUT"
kubectl apply -f k8s/05-agent-serviceaccount.yaml -f k8s/30-agent-netpol.yaml -f k8s/70-validator.yaml >/dev/null
. validator/validate.sh        # also brings pod_done (infra/pod-wait.sh)
now() { python3 -c 'import time; print(time.time())'; }
echo "control baseline:   $(validate "v-$ROUND-baseline" baseline)"     | tee "results/task-$ROUND-controls.txt"
echo "control maintainer: $(validate "v-$ROUND-maintainer" maintainer)" | tee -a "results/task-$ROUND-controls.txt"
for i in $(seq 1 "$N"); do
  if (( i % 2 )); then order="runc kata-qemu"; else order="kata-qemu runc"; fi
  for RT in $order; do
    rid="$ROUND-${RT%%-*}-$i"; name="agent-$rid"
    if [ "$RT" = runc ]; then line=""; else line="runtimeClassName: $RT"; fi
    nonce="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    sed -e "s/NAME/$name/" -e "s/RUNTIME_LINE/$line/" -e "s/\"RUN_ID\"/\"$rid\"/" -e "s/RESULT_NONCE_VALUE/$nonce/" k8s/60-agent-pod.yaml | kubectl apply -f - >/dev/null
    t0=$(now)
    pod_done lab-agent "$name" 960
    wall=$(python3 -c 'import sys; print(round(float(sys.argv[2]) - float(sys.argv[1]), 1))' "$t0" "$(now)")
    phase=$(kubectl -n lab-agent get pod "$name" -o jsonpath='{.status.phase}/{.status.reason}')
    res=$(kubectl -n lab-agent logs "$name" 2>/dev/null | python3 agent/result.py "$nonce" || true)
    [ -n "$res" ] || res='{"outcome":"no_result","patch":"","report_lines_rejected":0}'
    echo "$res" | python3 -c 'import json,sys; sys.stdout.write(json.load(sys.stdin).get("patch",""))' > "$PDIR/$rid.diff"
    val=$(validate "v-$rid" patch "$PDIR/$rid.diff"); [ -n "$val" ] || val='{"valid":false,"reasons":["no validation output"]}'
    python3 - "$ROUND" "$RT" "$i" "$rid" "$wall" "$phase" "$res" "$val" >> "$OUT" <<'PY'
import json, sys
rnd, rt, i, rid, wall, phase, res, val = sys.argv[1:]
r = json.loads(res); r.pop("patch", None)
print(json.dumps({"round": rnd, "run": rid, "runtime": rt, "i": int(i), "pod_phase": phase, "pod_wall_s": float(wall), "agent": r, "validation": json.loads(val)}))
PY
    tail -1 "$OUT" | python3 -c 'import json,sys; r=json.load(sys.stdin); a=r["agent"]; v=r["validation"]; print(r["run"], a.get("outcome"), "calls", a.get("model_calls"), "total_s", a.get("total_s"), "valid", v.get("valid"), v.get("summary"), "| other RESULT lines rejected:", a.get("report_lines_rejected"))'
    kubectl -n lab-agent delete pod "$name" --wait=false >/dev/null
  done
done
