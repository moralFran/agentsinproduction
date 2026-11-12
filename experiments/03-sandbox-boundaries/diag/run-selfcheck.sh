#!/usr/bin/env bash
# Runs ON aip-kata-01. The harness's fixed self-check (agent/selfcheck.py) as PID 1 of a pod made from the agent's
# image and spec, once per runtime. No model call. It shows, with fixed commands: pipefail, the nonce kept from the
# commands, /proc/1 closed to them, nothing left running after a command, a report that runs nothing from the
# workspace's git config; and the facts of the pod (user, seccomp mode, read-only root filesystem, kernel). The pod
# exits 1 if a check fails, so it ends as Failed and the wait returns at once (infra/pod-wait.sh).
# Then the runner's side: the report is picked by nonce (agent/result.py), and any other RESULT line is counted.
# Writes results/selfcheck-$RUN.jsonl and the two pod logs.   usage: RUN=<id> diag/run-selfcheck.sh
set -euo pipefail
export KUBECONFIG=~/.kube/config; cd "$(dirname "$0")/.."; . infra/out.sh; . infra/pod-wait.sh
OUT="$(out selfcheck jsonl)"; : > "$OUT"
kubectl apply -f k8s/30-agent-netpol.yaml >/dev/null
for RT in runc kata-qemu; do
  rt="${RT%%-*}"; name="selfcheck-$rt"; LOG="$(out "selfcheck-$rt" log)"
  if [ "$RT" = runc ]; then line=""; else line="runtimeClassName: $RT"; fi
  nonce="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  kubectl -n lab-agent delete pod "$name" --ignore-not-found --wait=true >/dev/null
  sed -e "s/NAME/$name/" -e "s/RUNTIME_LINE/$line/" -e "s/\"RUN_ID\"/\"$name\"/" -e "s/RESULT_NONCE_VALUE/$nonce/" k8s/60-agent-pod.yaml \
    | sed -E 's/^(    image: aip-agent:[0-9]+)$/\1\n    command: ["python3", "-u", "\/agent\/selfcheck.py"]/' | kubectl apply -f - >/dev/null
  [ "$(kubectl -n lab-agent get pod "$name" -o jsonpath='{.spec.containers[0].command[2]}')" = /agent/selfcheck.py ] || { echo "$name would run the agent; aborting"; kubectl -n lab-agent delete pod "$name" --wait=false; exit 1; }
  t0=$(date +%s); pod_done lab-agent "$name" 300
  phase="$(kubectl -n lab-agent get pod "$name" -o jsonpath='{.status.phase}')"
  kubectl -n lab-agent logs "$name" > "$LOG" 2>&1 || true
  picked="$(python3 agent/result.py "$nonce" < "$LOG")"
  python3 - "$RT" "$phase" "$(( $(date +%s) - t0 ))" "$LOG" "$picked" >> "$OUT" <<'PY'
import json, sys
rt, phase, secs, log, picked = sys.argv[1:]
line = next((l for l in open(log) if l.startswith("SELFCHECK ")), None)
print(json.dumps({"runtime": rt, "pod_phase": phase, "pod_wall_s": int(secs), "selfcheck": json.loads(line[10:]) if line else None, "report_picked_by_nonce": json.loads(picked)}))
PY
  tail -1 "$OUT" | python3 -c '
import json, sys
r = json.load(sys.stdin); s = r["selfcheck"] or {"checks": [], "facts": {}, "failed": ["no SELFCHECK line in the log"]}
print("==", r["runtime"] + ":", "pod", r["pod_phase"], "after", r["pod_wall_s"], "s")
for c in s["checks"]: print(("ok  " if c["ok"] else "n/a " if c["ok"] is None else "FAIL"), c["check"], "-", c["detail"])
print("facts:", ", ".join(k + " " + str(v) for k, v in s["facts"].items()))
p = r["report_picked_by_nonce"]
print("report picked by nonce: outcome", p.get("outcome"), "- other RESULT lines in the log, rejected:", p.get("report_lines_rejected"))'
  kubectl -n lab-agent delete pod "$name" --wait=false >/dev/null
done
