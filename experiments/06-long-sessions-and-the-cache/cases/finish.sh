#!/usr/bin/env bash
# Runs ON aip-ctx-01 under nohup. Server-side end of the reproduction (experiment 05), no model call anywhere:
#  1. waits for the sample queue to end; samples that came back as infrastructure errors are set aside and rerun (2 rounds);
#  2. derives the F2P/P2P lists of every task                                  -> /srv/ci/logs/finish.lists
#  3. the two validator controls of every task, criteria E10 (two stages)      -> /srv/ci/logs/finish.all
# Progress in /srv/ci/logs/finish.log. Stop it with: pkill -f finish.sh; pkill -f validate.py; pkill -f queue_team.py
set -uo pipefail
cd "$(dirname "$0")/.."; export KUBECONFIG=~/.kube/config
L=/srv/ci/logs/finish.log; say() { echo "$(date -u +%H:%M:%S) $*" >> "$L"; }
TASKS="${TASKS:-T4 T2 T3 T5 T6 T7 T8}"
while pgrep -f "[q]ueue_team.py" >/dev/null; do sleep 30; done
say "queue ended"
for round in 1 2; do
  n=$(python3 - <<'PY'
import glob, json, os
n = 0
for f in sorted(glob.glob("/srv/ci/repro/T*/*.json")):
    r = json.load(open(f))
    if r["executor"].get("outcome") != "sampled" or r.get("result") is None:
        os.rename(f, f"{f}.set-aside.{int(os.path.getmtime(f))}"); n += 1
        open("/srv/ci/logs/finish.log", "a").write(f"  set aside and rerun: {f} ({r['executor'].get('outcome')}: {str(r['executor'].get('why', ''))[:120]})\n")
print(n)
PY
)
  say "round $round: $n samples to rerun"
  [ "$n" = 0 ] && break
  python3 cases/queue_team.py $TASKS >> /srv/ci/logs/queue-rerun.log 2>&1
done
for t in T1 $TASKS; do python3 cases/team_host.py derive "$t" > "/srv/ci/logs/derive-$t.log" 2>&1; say "derive $t: $(cut -c1-330 /srv/ci/logs/derive-$t.log)"; done
date -u > /srv/ci/logs/finish.lists; say "LISTS DONE"
# Validator controls under criteria E10 (two stages), both for every task, cheapest tasks first. Task 1's controls of
# 18:40 (rule before E10: 3 samples of every job) are kept as T1-*.before-E10.json and task 1 is run again at the end.
for k in gold empty; do [ -f "/srv/ci/validate/T1-$k.json" ] && ! grep -q decided_in_stage "/srv/ci/validate/T1-$k.json" && mv "/srv/ci/validate/T1-$k.json" "/srv/ci/validate/T1-$k.before-E10.json"; done
for t in ${CONTROL_ORDER:-T4 T6 T5 T7 T3 T2 T8 T1}; do
  bash cases/controls.sh "$t" 3 both > "/srv/ci/logs/controls-$t.log" 2>&1; say "$(grep CONTROL /srv/ci/logs/controls-$t.log | tr '\n' ' ')"; done
date -u > /srv/ci/logs/finish.all; say "ALL DONE"
