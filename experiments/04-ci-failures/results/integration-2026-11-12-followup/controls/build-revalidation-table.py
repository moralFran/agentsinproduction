#!/usr/bin/env python3
"""Follow-up integration (2026-11-12), runs on our own files. One row per archived attempt: the archived outcome, the
outcome of the first integration round (results/integration-2026-11-12/revalidation.csv, harness 1160dcd) and the
outcome of this round (revalidation/<case>/<sha>.json, harness d5e1195 with the VM-only fix). Writes revalidation.csv/.md.
usage: build-revalidation-table.py <experiment-dir> <followup-dir>"""
import collections, csv, hashlib, json, pathlib, sys
exp, integ = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
MAIN = ["gobwas-ws-a567dfd6", "sigstore-cosign-1ab7015b", "tdewolff-minify-fa882446", "mark3labs-mcp-go-1969a6b9", "alicebob-miniredis-ce093519",
        "ludwig-ai-ludwig-6a122a8e", "pyinfra-dev-pyinfra-e7e42b68", "rmax-scrapy-redis-8d8672f2"]
EXCLUDED = ["nkanaev-yarr-957e81dd", "boyter-scc-4288f7c8", "openbyteinc-quantdinger-733f7bc7"]
GREEN = {"green_no_hidden_tests", "green_passes_hidden", "green_fails_hidden"}
first = {r["run"]: r for r in csv.DictReader(open(exp / "results" / "integration-2026-11-12" / "revalidation.csv"))}
rows, empty = [], []
for version in ("v1", "v2"):
    for line in open(exp / "results" / f"attempts-{version}.jsonl"):
        a = json.loads(line); data = (exp / "results" / "patches" / version / f"{a['run']}.diff").read_bytes()
        old = a["executor"].get("outcome")
        if not data.strip(): empty.append((a["run"], a["case"], old)); continue
        digest = hashlib.sha256(data).hexdigest(); f = integ / "revalidation" / a["case"] / f"{digest[:12]}.json"
        rec = json.loads(f.read_text()) if f.exists() else None; r = (rec or {}).get("result") or {}
        new = r.get("outcome") if rec else "not_run"; one = first[a["run"]]
        count = lambda phase: "" if f"{phase}_runs" not in r else f"{sum(x['rc'] == 0 for x in r[f'{phase}_runs'])}/{len(r[f'{phase}_runs'])}"
        rows.append({"run": a["run"], "version": version, "case": a["case"], "group": "main" if a["case"] in MAIN else "excluded", "patch_sha256_12": digest[:12],
                     "archived_outcome": old, "first_round_outcome": one["new_outcome"], "first_round_suite": one["new_suite_pass_of_3"], "first_round_hidden": one["new_hidden_pass_of_3"],
                     "outcome": new, "suite_pass_of_3": count("suite"), "hidden_pass_of_3": count("hidden"),
                     "vs_archive": "not run" if new == "not_run" else ("same" if new == old else "DIFFERENT"),
                     "vs_first_round": "not run" if new == "not_run" else ("same" if (new, count("suite"), count("hidden")) == (one["new_outcome"], one["new_suite_pass_of_3"], one["new_hidden_pass_of_3"]) else "DIFFERENT"),
                     "why": (r.get("why") or ("the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none" if old == "green_no_hidden_tests" and "hidden_runs" in r else ""))[:300]})
order = {c: i for i, c in enumerate(MAIN + EXCLUDED)}; rows.sort(key=lambda r: (order[r["case"]], r["version"], r["run"]))
with open(integ / "revalidation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
done = [r for r in rows if r["outcome"] != "not_run"]; da = [r for r in done if r["vs_archive"] == "DIFFERENT"]; d1 = [r for r in done if r["vs_first_round"] == "DIFFERENT"]
distinct = {(r["case"], r["patch_sha256_12"]) for r in done}
L = ["# Re-validation of the archived agent patches, follow-up round (cluster, 2026-11-12)", "",
     "Validator of the follow-up harness (`cases/validate.py`, executor of commit e7858e9/d5e1195 **plus the VM-only `safe.directory` fix**, see",
     "`harness-fix/`): three fresh suite pods, then three fresh hidden-test pods, both phases with the broken-tree Go cache; the integrity check",
     "fingerprints Git metadata, the index (after one refresh) and every `.gitignore`. **Not a re-classification**: the archived outcomes stand.", "",
     f"- Non-empty archived patches: {len(rows)} attempts; re-validated here: {len(done)} ({len(distinct)} distinct patches); not run: {len(rows) - len(done)}; empty patches (not validated): {len(empty)}.",
     f"- **Against the archive: {len(done) - len(da)} same, {len(da)} different.**",
     f"- **Against the first integration round (outcome and both 3/3 counts): {len(done) - len(d1)} same, {len(d1)} different.**",
     f"- Outcome `test_changed_tree`: {sum(r['outcome'] == 'test_changed_tree' for r in done)} attempts. Infrastructure errors or timeouts: {sum(r['outcome'] in ('infra_error', 'timeout') for r in done)}.", ""]
for title, diff, other in (("Differences from the archive", da, "first_round_outcome"), ("Differences from the first integration round", d1, "first_round_outcome")):
    L += [f"## {title}", ""]
    if not diff: L += ["None.", ""]; continue
    L += ["| Run | Case | Archived | First round | This round | Suite | Hidden | Reason given |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['run']} | {r['case']} | {r['archived_outcome']} | {r['first_round_outcome']} ({r['first_round_suite'] or '-'}, {r['first_round_hidden'] or '-'}) | {r['outcome']} | {r['suite_pass_of_3'] or '-'} | {r['hidden_pass_of_3'] or '-'} | {r['why']} |" for r in diff] + [""]
L += ["## Outcome counts", "", "| Outcome | Archived | First round | This round |", "|---|---|---|---|"]
ca, c1, cn = (collections.Counter(r[k] for r in done) for k in ("archived_outcome", "first_round_outcome", "outcome"))
L += [f"| {k} | {ca.get(k, 0)} | {c1.get(k, 0)} | {cn.get(k, 0)} |" for k in sorted(set(ca) | set(c1) | set(cn))] + [""]
main_rows = [r for r in rows if r["group"] == "main"]; main_empty = [e for e in empty if e[1] in MAIN]
cnt = lambda key, pred, sub=main_rows: sum(pred(r[key]) for r in sub)
ver = lambda key, v: sum(r[key] in GREEN for r in main_rows if r["version"] == v)
ws = [r for r in main_rows if r["case"] == "gobwas-ws-a567dfd6"]
L += ["## Published numbers of the main analysis, recomputed (arithmetic only)", "",
      "Main analysis = 8 cases x 3 repetitions x 2 versions. \"Green\" = any of the three green outcomes. Empty patches are not green in any column.", "",
      "| Number | Published (archive) | First round | This round |", "|---|---|---|---|"]
L += ["| Main-analysis attempts | " + " | ".join([str(len(main_rows) + len(main_empty))] * 3) + " |"]
for label, pred, sub in (("Green", GREEN.__contains__, main_rows), ("Green that failed the maintainer's hidden tests", "green_fails_hidden".__eq__, main_rows), ("... of those, gobwas/ws", "green_fails_hidden".__eq__, ws)):
    L.append(f"| {label} | " + " | ".join(str(cnt(k, pred, sub)) for k in ("archived_outcome", "first_round_outcome", "outcome")) + " |")
for v in ("v1", "v2"): L.append(f"| {v} green | " + " | ".join(str(ver(k, v)) for k in ("archived_outcome", "first_round_outcome", "outcome")) + " |")
L += ["", "All main-analysis patches were re-validated in this round." if all(r["outcome"] != "not_run" for r in main_rows) else "**Not every main-analysis patch was re-validated in this round: the last column is incomplete.**", "",
      "## One row per attempt", "", "| Run | Case | Archived | First round | This round | Suite of 3 | Hidden of 3 | vs archive | vs first round |", "|---|---|---|---|---|---|---|---|---|"]
L += [f"| {r['run']} | {r['case']} | {r['archived_outcome']} | {r['first_round_outcome']} | {r['outcome']} | {r['suite_pass_of_3'] or '-'} | {r['hidden_pass_of_3'] or '-'} | {r['vs_archive']} | {r['vs_first_round']} |" for r in rows]
L += ["", "Attempts with an empty patch (not validated): " + ", ".join(run for run, _, _ in empty) + ".", ""]
(integ / "revalidation.md").write_text("\n".join(L))
print(f"{len(done)} re-validated | vs archive: {len(done) - len(da)} same, {len(da)} different | vs first round: {len(done) - len(d1)} same, {len(d1)} different | test_changed_tree: {sum(r['outcome'] == 'test_changed_tree' for r in done)}")
for r in d1: print("DIFF-1", r["run"], r["case"], r["first_round_outcome"], r["first_round_suite"], r["first_round_hidden"], "->", r["outcome"], r["suite_pass_of_3"], r["hidden_pass_of_3"], r["why"][:200])
