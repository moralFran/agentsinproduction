#!/usr/bin/env python3
"""Control for the "errors after a compaction" count (criteria E15, 27/11/2026, added after the runs).

In the compacted runs, a compaction always lands right after a phase ends: at_call = phase end + 1. So the 20-call windows
around it also straddle a phase change, and a new phase can bring failing test runs of its own. The runs without
compaction end the same phases, so they get the same windows at the same points:
  before = commands of model calls (k-21, k-1],  after = commands of model calls (k, k+20],  k = phase end + 1
These are the same windows live_report.py uses for each compaction. An error is a command with exit code != 0, failing test
runs included. Windows near a run's end are shorter. Two phase ends that are close share calls, so their windows overlap.

Reads the journal of the live round (results/attempts-<round>.jsonl, kept in the private audit archive). Writes
report/<round>-phase-errors.json with counts only: no command text, no paths, no app content.
usage: phase_errors.py <attempts.jsonl> <out.json>"""
import itertools, json, statistics, sys

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
out = {"runs": [], "by_condition": {}}
deltas = {}
for r in rows:
    a, cond = r["agent"], r["config"]
    cmds = a.get("commands", [])
    errs = lambda lo, hi: sum(1 for x in cmds if lo < x.get("call", 0) <= hi and x.get("rc", 0) != 0)
    n = lambda lo, hi: sum(1 for x in cmds if lo < x.get("call", 0) <= hi)
    comp = {k["at_call"] for k in a.get("compactions", [])}
    pts = []
    for p in a.get("phases", []):
        k = p["call"] + 1
        pts.append({"at_call": k, "compacted_here": k in comp, "errors_20_before": errs(k - 21, k - 1), "commands_20_before": n(k - 21, k - 1),
                    "errors_20_after": errs(k, k + 20), "commands_20_after": n(k, k + 20)})
        deltas.setdefault(cond, []).append(pts[-1]["errors_20_after"] - pts[-1]["errors_20_before"])
    if cond == "L2":   # the windows must be the ones of report/<round>-live.json for every compaction
        assert comp == {p["at_call"] for p in pts}, (r["run"], comp)
    out["runs"].append({"run": r["run"], "condition": cond, "phase_ends": pts})
for cond in sorted(deltas):
    pts = [p for x in out["runs"] if x["condition"] == cond for p in x["phase_ends"]]
    out["by_condition"][cond] = {"points": len(pts), "errors_before": sum(p["errors_20_before"] for p in pts),
                                 "errors_after": sum(p["errors_20_after"] for p in pts),
                                 "rose": sum(p["errors_20_after"] > p["errors_20_before"] for p in pts),
                                 "fell": sum(p["errors_20_after"] < p["errors_20_before"] for p in pts),
                                 "same": sum(p["errors_20_after"] == p["errors_20_before"] for p in pts)}
# exact one-sided permutation test on the per-point change (after - before), compacted vs not; points are not independent
# (two runs per condition, overlapping windows), so this is a guide to the size of the signal, not a significance claim
c, u = deltas["L2"], deltas["L0"]; allv = c + u; obs = statistics.mean(c) - statistics.mean(u)
tot = hit = 0
for idx in itertools.combinations(range(len(allv)), len(c)):
    g = [allv[i] for i in idx]; h = [allv[i] for i in range(len(allv)) if i not in idx]
    tot += 1; hit += statistics.mean(g) - statistics.mean(h) >= obs - 1e-9
out["permutation"] = {"mean_change_L2": round(statistics.mean(c), 3), "mean_change_L0": round(statistics.mean(u), 3),
                      "one_sided_p": round(hit / tot, 4), "splits": tot}
json.dump(out, open(sys.argv[2], "w"), indent=1)
for cond, v in out["by_condition"].items():
    print(cond, v)
print(out["permutation"])
