#!/usr/bin/env python3
"""Integration (2026-11-12), runs on our own files. Joins the archived attempts (results/attempts-v1/v2.jsonl, read only)
with the re-validation results (revalidation/<case>/<sha>.json) and writes revalidation.csv and revalidation.md.
usage: build-revalidation-table.py <experiment-dir> <integration-dir>"""
import collections, csv, hashlib, json, pathlib, sys
exp, integ = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
MAIN = ["gobwas-ws-a567dfd6", "sigstore-cosign-1ab7015b", "tdewolff-minify-fa882446", "mark3labs-mcp-go-1969a6b9", "alicebob-miniredis-ce093519",
        "ludwig-ai-ludwig-6a122a8e", "pyinfra-dev-pyinfra-e7e42b68", "rmax-scrapy-redis-8d8672f2"]
EXCLUDED = ["nkanaev-yarr-957e81dd", "boyter-scc-4288f7c8", "openbyteinc-quantdinger-733f7bc7"]
GREEN = {"green_no_hidden_tests", "green_passes_hidden", "green_fails_hidden"}
rows, empty = [], []
for version in ("v1", "v2"):
    for line in open(exp / "results" / f"attempts-{version}.jsonl"):
        a = json.loads(line); data = (exp / "results" / "patches" / version / f"{a['run']}.diff").read_bytes()
        old = a["executor"].get("outcome")
        if not data.strip(): empty.append((a["run"], a["case"], old)); continue
        digest = hashlib.sha256(data).hexdigest(); f = integ / "revalidation" / a["case"] / f"{digest[:12]}.json"
        rec = json.loads(f.read_text()) if f.exists() else None; r = (rec or {}).get("result") or {}
        new = r.get("outcome") if rec else "not_run"
        sp = r.get("suite_pass", sum(x["rc"] == 0 for x in r["suite_runs"]) if "suite_runs" in r else None)
        hp = r.get("hidden_pass", sum(x["rc"] == 0 for x in r["hidden_runs"]) if "hidden_runs" in r else None)
        rows.append({"run": a["run"], "version": version, "case": a["case"], "group": "main" if a["case"] in MAIN else "excluded",
                     "patch_sha256_12": digest[:12], "shared_with": "", "archived_outcome": old, "archived_suite_pass": a["executor"].get("suite_pass"),
                     "archived_hidden_runs": len(a["executor"].get("hidden_runs", [])) or "", "new_outcome": new,
                     "new_suite_pass_of_3": "" if sp is None else f"{sp}/{len(r.get('suite_runs', []))}",
                     "new_hidden_pass_of_3": "" if hp is None else f"{hp}/{len(r.get('hidden_runs', []))}",
                     "same": "not run" if new == "not_run" else ("same" if new == old else "DIFFERENT"),
                     "why": (r.get("why") or ("the current preparation gives this case hidden tests; the archived run had none" if old == "green_no_hidden_tests" and "hidden_runs" in r else ""))[:160]})
groups = collections.defaultdict(list)
for r in rows: groups[(r["case"], r["patch_sha256_12"])].append(r["run"])
for r in rows: r["shared_with"] = " ".join(x for x in groups[(r["case"], r["patch_sha256_12"])] if x != r["run"])
order = {c: i for i, c in enumerate(MAIN + EXCLUDED)}
rows.sort(key=lambda r: (order[r["case"]], r["version"], r["run"]))
with open(integ / "revalidation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

done = [r for r in rows if r["same"] != "not run"]; diff = [r for r in done if r["same"] == "DIFFERENT"]
L = ["# Re-validation of the archived agent patches with the hardened validator (cluster, 2026-11-12)", "",
     "What the new validator (`cases/validate.py`: three fresh suite pods, then three fresh hidden-test pods) says about each archived",
     "patch, next to the outcome the archived executor recorded. **This is not a re-classification**: the archived outcomes stand on the",
     "harness that produced them. The archived executor ran the suite 3 times and the hidden tests once in ONE pod; the new one runs",
     "each sample in its own pod. Byte-identical patches of a case were validated once (column *same patch as*).", "",
     f"- Attempts in the archive: {len(rows) + len(empty)}; with an empty patch (not validated, nothing to apply): {len(empty)}; non-empty: {len(rows)}.",
     f"- Distinct patches: {len(groups)}. Re-validated: {len(done)} attempts ({len({(r['case'], r['patch_sha256_12']) for r in done})} distinct patches); not run: {len(rows) - len(done)}.",
     f"- **Same outcome: {len(done) - len(diff)} of {len(done)}. Different: {len(diff)}.**", ""]
if diff:
    L += ["## Differences", "", "| Run | Case | Archived | New validator | Suite | Hidden | Reason given |", "|---|---|---|---|---|---|---|"]
    L += [f"| {r['run']} | {r['case']} | {r['archived_outcome']} | {r['new_outcome']} | {r['new_suite_pass_of_3']} | {r['new_hidden_pass_of_3']} | {r['why']} |" for r in diff] + [""]
    if any(r["case"] == "nkanaev-yarr-957e81dd" for r in diff):
        L += ["nkanaev/yarr: the maintainer's fix is only a test fixture (`src/parser/fixtures/atom/link-in-id.xml`). The archived preparation did not treat",
              "`fixtures/` as test data, so the case had no hidden tests (README, tool note of 12/11; amendment 24 of `criteria.md`, which already",
              "keeps yarr out of the main analysis). The current `cases/prep.py` does, so the fixture change is now the hidden test: the six patches",
              "pass the original suite 3/3 and fail it 0/3 once the maintainer's fixture is in place. Reproduction control for the case: maintainer's",
              "fix 3/3 pass, broken code plus the fixture 3/3 pass (`discriminates` false: the fixture is the fix).", ""]
L += ["## Outcome counts (re-validated attempts)", "", "| Outcome | Archived | New validator |", "|---|---|---|"]
ca, cn = collections.Counter(r["archived_outcome"] for r in done), collections.Counter(r["new_outcome"] for r in done)
L += [f"| {k} | {ca.get(k, 0)} | {cn.get(k, 0)} |" for k in sorted(set(ca) | set(cn))] + [""]
L += ["## Published numbers, recomputed with the new validator's outcomes (arithmetic only)", "",
      "Main analysis = 8 cases x 3 repetitions x 2 versions. \"Green\" = suite 3/3 and accepted by the validator (any of the three green outcomes).",
      "Attempts with an empty patch keep their archived outcome (`no_patch`: not green in either column).", "",
      "| Number | Published (archive) | What the new validator says |", "|---|---|---|"]
main_rows = [r for r in rows if r["group"] == "main"]; main_empty = [e for e in empty if e[1] in MAIN]
covered = all(r["same"] != "not run" for r in main_rows)
def count(key, pred): return sum(pred(r[key]) for r in main_rows)
def per_version(key, v): return sum(r[key] in GREEN for r in main_rows if r["version"] == v)
gw = lambda key: sum(r[key] == "green_fails_hidden" for r in main_rows if r["case"] == "gobwas-ws-a567dfd6")
L += [f"| Main-analysis attempts | {len(main_rows) + len(main_empty)} | {len(main_rows) + len(main_empty)} |",
      f"| Green | {count('archived_outcome', GREEN.__contains__)} | {count('new_outcome', GREEN.__contains__)} |",
      f"| Green that failed the maintainer's hidden tests | {count('archived_outcome', 'green_fails_hidden'.__eq__)} | {count('new_outcome', 'green_fails_hidden'.__eq__)} |",
      f"| ... of those, gobwas/ws | {gw('archived_outcome')} | {gw('new_outcome')} |",
      f"| v1 green | {per_version('archived_outcome', 'v1')} | {per_version('new_outcome', 'v1')} |",
      f"| v2 green | {per_version('archived_outcome', 'v2')} | {per_version('new_outcome', 'v2')} |", "",
      "All main-analysis patches were re-validated." if covered else "**Not every main-analysis patch was re-validated: the right-hand column is incomplete.**", ""]
L += ["## One row per attempt", "", "| Run | Case | Archived outcome | New outcome | Suite passes of 3 | Hidden passes of 3 | Same? | Same patch as |", "|---|---|---|---|---|---|---|---|"]
L += [f"| {r['run']} | {r['case']} | {r['archived_outcome']} | {r['new_outcome']} | {r['new_suite_pass_of_3'] or '-'} | {r['new_hidden_pass_of_3'] or '-'} | {r['same']} | {r['shared_with'] or '-'} |" for r in rows]
L += ["", "## Attempts with an empty patch (not validated)", "", ", ".join(f"{run} ({case.rsplit('-', 1)[0]})" for run, case, _ in empty), ""]
(integ / "revalidation.md").write_text("\n".join(L))
print(f"{len(done)} re-validated, {len(done) - len(diff)} same, {len(diff)} different, {len(rows) - len(done)} not run")
for r in diff: print("DIFF", r["run"], r["case"], r["archived_outcome"], "->", r["new_outcome"], r["new_suite_pass_of_3"], r["new_hidden_pass_of_3"], r["why"])
