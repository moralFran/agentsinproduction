#!/usr/bin/env python3
"""Runs ON aip-ci-01. Freezes the case list. Decision of Francisco (11/11): the set is EVERY candidate among the 113 mined
that reproduces, no selection, once every candidate is settled; floor of 8 (below it: no freeze, report). Originally
(criteria.md §15) the first 30 candidates, in mining order (Go and Python
interleaved, the order the workers claim them), whose reproduction verdict is "reproduced" (broken fails 3/3, maintainer's
fix passes 3/3). Writes cases/cases.csv, cases/intermittent.csv and cases/not-reproduced.csv, and, for each frozen case,
the failure the agent will be shown (<case>/failure.txt: the broken tree's test output from our reproduction).
Prints the sha256 of cases.csv. Refuses to run twice (the list is frozen once). Future runs also require a clean
maintainer integrity control in reproduction, so suite-generated output cannot make every agent patch fail validation.
A reasoned include/exclude decision tied to that record is required when an applicable hidden control does not
discriminate, when a Go case's broken tree did not compile in preparation, or when the maintainer's fix does not pass
with the agent's dependency cache."""
import csv, hashlib, itertools, json, os, re, sys
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
if os.path.exists("cases/cases.csv"): sys.exit("cases/cases.csv already exists: the list is frozen")
rd = lambda p: [json.loads(l) for l in open(p)] if os.path.exists(p) else []
go, py = rd("mining/candidates-go.jsonl"), rd("mining/candidates-python.jsonl")
order = [x for pair in itertools.zip_longest(go, py) for x in pair if x]
cid = lambda c: re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
rep = {r["id"]: r for r in rd("cases/repro.jsonl")}
skip = set(open("cases/excluded-recheck.txt").read().split()) if os.path.exists("cases/excluded-recheck.txt") else set()
order = [c for c in order if cid(c) not in skip]     # excluded by the corrected criterion 9: not candidates any more
frozen, inter, notrep = [], [], []
decisions_path = 'cases/eligibility-decisions.json'
decisions = json.load(open(decisions_path)) if os.path.exists(decisions_path) else {}
reviewed = {}
for c in order:
    r = rep.get(cid(c))
    if not r: continue
    if r["verdict"] == "reproduced":
        if r.get("integrity_control", {}).get("outcome") != "clean":
            sys.exit(f"case {cid(c)} lacks a clean maintainer integrity control: rerun cases/repro.sh before freezing")
        control = r.get('hidden_control', {})
        if not isinstance(control.get('applicable'), bool):
            sys.exit(f"case {cid(c)} lacks an explicit hidden-control applicability result: rerun cases/repro.sh")
        reasons = []
        if control['applicable'] and control.get('discriminates') is not True:
            reasons.append('the hidden control does not discriminate')
        if c['language'] == 'Go':
            compiles = r.get('prep_control', {}).get('broken_compiles')
            if not isinstance(compiles, bool):
                sys.exit(f"case {cid(c)} lacks the broken-tree compile result: rerun its preparation and cases/repro.sh")
            if not compiles: reasons.append('the broken tree did not compile in preparation (its own error, or a missing module?)')
            cache = r.get('cache_control', {})
            if not isinstance(cache.get('applicable'), bool):
                sys.exit(f"case {cid(c)} lacks the agent-cache control of the maintainer's fix: rerun cases/repro.sh")
            if cache['applicable'] and cache.get('integrity') == 'changed':
                reasons.append("the maintainer's fix changes the working tree with the agent's dependency cache, so validation "
                               "would record test_changed_tree for every patch: " + str(cache.get('why', ''))[:200])
            elif cache['applicable'] and (cache.get('passes') is not True or cache.get('integrity') != 'clean'):
                reasons.append("the maintainer's fix does not pass with the agent's dependency cache")
        if reasons:
            digest = hashlib.sha256(json.dumps(r, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            decision = decisions.get(cid(c), {})
            if (not isinstance(decision, dict) or decision.get('decision') not in ('include', 'exclude')
                    or not isinstance(decision.get('reason'), str) or not decision['reason'].strip()
                    or not isinstance(decision.get('reviewer'), str) or not decision['reviewer'].strip()
                    or decision.get('repro_sha256') != digest):
                sys.exit(f"case {cid(c)} needs an eligibility decision in {decisions_path} ({'; '.join(reasons)}): include/exclude, reason, reviewer, repro_sha256={digest}")
            reviewed[cid(c)] = decision
            if decision['decision'] == 'exclude':
                notrep.append((c, {**r, 'verdict': 'excluded_after_eligibility_review'})); continue
        frozen.append((c, r))
    elif r["verdict"] == "intermittent": inter.append((c, r))
    elif r["verdict"] != "reproduced": notrep.append((c, r))
# every candidate must be settled (a verdict, or a failed preparation)
pf = set()
for l in open("cases/prep-out/prep.jsonl"):
    m = re.search(r'"id": "([^"]+)", "prep": "fail"|PREP_FAIL ([^:]+):', l)
    if m: pf.add(m.group(1) or m.group(2))
pending = [cid(c) for c in order if cid(c) not in rep and cid(c) not in pf]
if pending: sys.exit(f"{len(pending)} candidates not settled yet: {pending[:5]}")
if len(frozen) < 8: sys.exit(f"only {len(frozen)} reproduced cases (floor 8): not freezing")
F = ["case_id", "repo", "language", "broken_sha", "fix_sha", "workflow", "failed_job", "workdir", "test_cmd", "hidden_tests", "hidden_cmd", "failed_run"]
with open("cases/cases.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(F)
    for c, r in frozen:
        sm = json.load(open(f"/srv/ci/secret/{r['id']}/meta.json"))
        w.writerow([r["id"], c["repo"], c["language"], c["broken_sha"], c["fix_sha"], c["workflow"], c["failed_job"], sm.get("workdir", "."),
                    sm["test_cmd"], "yes" if sm.get("hidden_cmd") else "no", sm.get("hidden_cmd", ""), c["failed_run"]])
        open(f"/srv/ci/cases/{r['id']}/failure.txt", "w").write(r["broken"].get("output_head", ""))
for name, rows in (("intermittent", inter), ("not-reproduced", notrep)):
    with open(f"cases/{name}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["case_id", "repo", "verdict", "broken_fail", "fixed_pass", "n"])
        for c, r in rows: w.writerow([r["id"], c["repo"], r["verdict"], r["broken_fail"], r["fixed_pass"], r["n"]])
with open('cases/eligibility-at-freeze.json', 'w') as f: json.dump(reviewed, f, indent=2)
print("sha256", hashlib.sha256(open("cases/cases.csv", "rb").read()).hexdigest(), "cases/cases.csv")
print(f"frozen {len(frozen)} (Go {sum(c['language'] == 'Go' for c, _ in frozen)}, Python {sum(c['language'] == 'Python' for c, _ in frozen)}); intermittent {len(inter)}; not reproduced {len(notrep)}")
