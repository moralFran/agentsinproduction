#!/usr/bin/env bash
# Runs ON THE MAC, from anywhere. Regenerates the reproduction report on aip-ci-01 and copies into this experiment folder
# only what holds no app source: tasks/repro-report.md, tasks.csv, tasks/cases/<T#>.json (case lists), and under
# tasks/records/ the snapshot/dependency records, the validator verdicts, the queue logs and the CONTROL lines.
# Raw samples, failure.txt and pod logs (compiler output with source lines) stay on the VM.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"; ZONE="${ZONE:-us-central1-a}"
D="$(cd "$(dirname "$0")/.." && pwd)"; T="$(mktemp -d)"
gcloud compute ssh aip-ci-01 --project "$AIP_PROJECT" --zone "$ZONE" --command 'cd ~/lab && rm -rf ~/results && mkdir -p ~/results/records && python3 cases/report_team.py --out ~/results >/dev/null && cp /srv/ci/logs/snapshot-T*.json /srv/ci/logs/deps-T*.json /srv/ci/validate/T*-*.json ~/results/records/ 2>/dev/null; cat /srv/ci/logs/queue-*.log /srv/ci/logs/queue.log > ~/results/records/queue.log 2>/dev/null; cat /srv/ci/logs/repro-T1.log /srv/ci/logs/repro-T4.log > ~/results/records/repro-T1-T4-direct.log 2>/dev/null; grep -h CONTROL /srv/ci/logs/controls-*.log > ~/results/records/controls.log 2>/dev/null; cp /srv/ci/logs/finish.log ~/results/records/ 2>/dev/null; cd ~/results && tar czf - .' > "$T/r.tgz"
mkdir -p "$D/tasks/cases" "$D/tasks/records" "$T/x"; tar xzf "$T/r.tgz" -C "$T/x"
cp "$T/x/repro-report.md" "$D/tasks/repro-report.md"; cp "$T/x/tasks.csv" "$D/tasks.csv"; cp "$T/x"/cases/*.json "$D/tasks/cases/"; cp "$T/x"/records/* "$D/tasks/records/"
rm -rf "$T"; grep -h CONTROL "$D/tasks/records/controls.log" | cut -c1-160 || true
