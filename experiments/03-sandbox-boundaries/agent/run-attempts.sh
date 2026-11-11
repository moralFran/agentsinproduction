#!/usr/bin/env bash
# Runs ON aip-kata-01. N attempts per runtime, alternating, one fresh pod each, NetworkPolicy applied.
# Each patch is then checked in a fresh validator pod (other namespace, no network, pristine checkout).
# Every invocation is a ROUND with its own id: pod names, gateway run ids, patch paths and the output file all carry
# it, so a smoke test can never be confused with a collection.   usage: run-attempts.sh <N> <round-id>
set -euo pipefail
export KUBECONFIG=~/.kube/config
N="${1:?attempts per runtime}"; ROUND="${2:?round id, e.g. main-20261111a}"
OUT="results/task-$ROUND.jsonl"; PDIR="results/patches/$ROUND"
[ ! -e "$OUT" ] || { echo "round $ROUND already exists; pick a new id"; exit 1; }
mkdir -p "$PDIR"; : > "$OUT"
kubectl apply -f k8s/30-agent-netpol.yaml -f k8s/70-validator.yaml >/dev/null
. "$(dirname "$0")/../validator/validate.sh"
echo "control baseline:   $(validate "v-$ROUND-baseline" baseline)"     | tee "results/task-$ROUND-controls.txt"
echo "control maintainer: $(validate "v-$ROUND-maintainer" maintainer)" | tee -a "results/task-$ROUND-controls.txt"
for i in $(seq 1 "$N"); do
  if (( i % 2 )); then order="runc kata-qemu"; else order="kata-qemu runc"; fi
  for RT in $order; do
    rid="$ROUND-${RT%%-*}-$i"; name="agent-$rid"
    if [ "$RT" = runc ]; then line=""; else line="runtimeClassName: $RT"; fi
    sed -e "s/NAME/$name/" -e "s/RUNTIME_LINE/$line/" -e "s/\"RUN_ID\"/\"$rid\"/" k8s/60-agent-pod.yaml | kubectl apply -f - >/dev/null
    t0=$(date +%s.%N)
    kubectl -n lab-agent wait --for=jsonpath='{.status.phase}'=Succeeded pod/"$name" --timeout=960s >/dev/null 2>&1 || true
    wall=$(echo "$(date +%s.%N) - $t0" | bc)
    phase=$(kubectl -n lab-agent get pod "$name" -o jsonpath='{.status.phase}/{.status.reason}')
    res=$(kubectl -n lab-agent logs "$name" | grep '^RESULT ' | sed 's/^RESULT //' || true)
    [ -n "$res" ] || res='{"outcome":"no_result","patch":""}'
    echo "$res" | python3 -c 'import json,sys; sys.stdout.write(json.load(sys.stdin).get("patch",""))' > "$PDIR/$rid.diff"
    val=$(validate "v-$rid" patch "$PDIR/$rid.diff"); [ -n "$val" ] || val='{"valid":false,"reasons":["no validation output"]}'
    python3 - "$ROUND" "$RT" "$i" "$rid" "$wall" "$phase" "$res" "$val" >> "$OUT" <<'PY'
import json, sys
rnd, rt, i, rid, wall, phase, res, val = sys.argv[1:]
r = json.loads(res); r.pop("patch", None)
print(json.dumps({"round": rnd, "run": rid, "runtime": rt, "i": int(i), "pod_phase": phase, "pod_wall_s": round(float(wall), 1), "agent": r, "validation": json.loads(val)}))
PY
    tail -1 "$OUT" | python3 -c 'import json,sys; r=json.load(sys.stdin); a=r["agent"]; v=r["validation"]; print(r["run"], a.get("outcome"), "calls", a.get("model_calls"), "total_s", a.get("total_s"), "valid", v.get("valid"), v.get("summary"))'
    kubectl -n lab-agent delete pod "$name" --wait=false >/dev/null
  done
done
