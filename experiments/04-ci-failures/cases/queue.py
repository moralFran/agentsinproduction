#!/usr/bin/env python3
"""Runs ON aip-ci-01. The queue of one round as a short table for the screen: each case of cases.csv and each repetition,
with its state (queued / agent running / validating / outcome). No version label beyond the round id given.
usage: queue.py <round-id>"""
import csv, hashlib, json, os, subprocess, sys
rnd = sys.argv[1]
cases = [r["case_id"] for r in csv.DictReader(open("cases/cases.csv"))]
done = {}
if os.path.exists(f"results/attempts-{rnd}.jsonl"):
    for l in open(f"results/attempts-{rnd}.jsonl"):
        r = json.loads(l); done[r["run"]] = r
pods = subprocess.run(["kubectl", "get", "pods", "-A", "--no-headers", "-o", "custom-columns=N:.metadata.name"], capture_output=True, text=True,
                      env={**os.environ, "KUBECONFIG": os.path.expanduser("~/.kube/config")}).stdout.split()
short = {"green_passes_hidden": "green +hidden", "green_no_hidden_tests": "green", "green_fails_hidden": "green, hidden FAIL",
         "ci_still_red": "still red", "ci_flaky_after_patch": "flaky", "rejected_by_validator": "rejected", "did_not_apply": "no apply", "no_patch": "no patch"}
print(f"{'case':30} {'rep 1':>14} {'rep 2':>14} {'rep 3':>14}")
for cid in cases:
    cells = []
    for rep in (1, 2, 3):
        run = f"{rnd}-{hashlib.md5((cid + chr(10)).encode()).hexdigest()[:8]}-r{rep}"
        if run in done: cells.append(short.get(done[run]["executor"].get("outcome"), done[run]["agent"].get("outcome", "?"))[:14])
        elif f"ag-{run}" in pods: cells.append("agent ...")
        elif f"va-{run}" in pods: cells.append("validating ...")
        else: cells.append("queued")
    print(f"{cid[:30]:30} {cells[0]:>14} {cells[1]:>14} {cells[2]:>14}")
print(f"done {len(done)} of {3 * len(cases)}")
