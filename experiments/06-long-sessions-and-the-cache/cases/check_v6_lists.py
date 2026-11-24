#!/usr/bin/env python3
"""Runs ON aip-ctx-01 after `team_host.py repro T8 --reps 1` (criteria E6, 23/11/2026). The snapshot (tar sha256) and
the dependency sets are byte-identical to experiment 05's, so its F2P/P2P lists for task 8 (3 + 3 samples) are reused
IF one baseline and one gold sample on this lab agree with them: every F2P case fails on baseline and passes on gold,
every P2P case passes on both. Then writes them as /srv/ci/secret/T8/cases.json and the agent's failure text from this
lab's baseline sample. Otherwise prints the disagreements and writes nothing (then: the full 3 + 3 reproduction).
usage: check_v6_lists.py <experiment 05's tasks/cases/T8.json>"""
import importlib.util, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("team_host", HERE / "team_host.py"); th = importlib.util.module_from_spec(spec); spec.loader.exec_module(th)
v6 = json.load(open(sys.argv[1]))
sm = th.secret_meta("T8")
assert sm["snapshot_tar_sha256"] == v6["snapshot_tar_sha256"], "snapshot differs from experiment 05's"
out1, failure = th.classify("T8", reps=1)
if out1["problems"]: sys.exit("samples with problems: " + "; ".join(out1["problems"][:5]))
key = lambda e: (e["job"], e["case"])
now = {}
for kind in ("f2p", "p2p", "excluded_fail_both", "unstable", "skipped", "broken_by_gold", "fixed_outside_commit_tests", "commit_tests_pass_both_out_of_scope"):
    for e in out1[kind]: now[key(e)] = kind
bad = [(k, "f2p", now.get(key(e))) for k in ["f2p"] for e in v6["f2p"] if now.get(key(e)) != "f2p"] + \
      [(k, "p2p", now.get(key(e))) for k in ["p2p"] for e in v6["p2p"] if now.get(key(e)) != "p2p"]
print(json.dumps({"v6_counts": v6["counts"], "this_lab_1+1": out1["counts"], "disagree": len(bad), "examples": bad[:10]}))
if bad: sys.exit(1)
(th.ROOT / "secret" / "T8" / "cases.json").write_text(json.dumps(v6))
header = "Output of the task's test files on this snapshot (failing cases only; from the lab's own run):\n\n"
text = failure if len(failure) <= 8000 else "[... earlier failures trimmed ...]\n" + failure[-8000:]
(th.ROOT / "cases" / "T8" / "failure.txt").write_text(header + text + "\n")
print("wrote /srv/ci/secret/T8/cases.json (experiment 05's lists) and /srv/ci/cases/T8/failure.txt")
