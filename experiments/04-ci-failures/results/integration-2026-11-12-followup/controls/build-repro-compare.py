#!/usr/bin/env python3
"""Follow-up integration (2026-11-12), runs on our own files. Reproduction of the 11 frozen cases in this round next to
the archive (cases/repro.jsonl) and to the first integration round (results/integration-2026-11-12/repro/repro.jsonl).
usage: build-repro-compare.py <experiment-dir> <followup-dir>"""
import csv, json, pathlib, sys
exp, integ = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
cases = list(csv.DictReader(open(exp / "cases" / "cases.csv")))
last = lambda p: {json.loads(l)["id"]: json.loads(l) for l in open(p) if l.strip()}
old, one = last(exp / "cases" / "repro.jsonl"), last(exp / "results" / "integration-2026-11-12" / "repro" / "repro.jsonl")
new = {}
for l in open(integ / "repro" / "repro.jsonl"):
    r = json.loads(l); new.setdefault(r["id"], []).append(r)
rc = lambda runs: "/".join("pass" if x.get("rc") == 0 else ("timeout" if x.get("rc") == 124 else ("none" if x.get("rc") is None else "fail")) for x in runs) or "-"
L = ["# Reproduction of the 11 frozen cases, follow-up round (2026-11-12), next to the archive and the first round", "",
     "Harness: commit d5e1195 (preparation and `repro.sh` as in dec7c18), executor e7858e9 **plus the VM-only `safe.directory` fix** (`harness-fix/`).",
     "New in this round: the checkout is restored before every sample; `prep_control.broken_compiles` (Go, from preparation); `cache_control` (Go: the",
     "maintainer's fix run 3 + 3 times with the agent's, broken-tree, module cache); the integrity check also fingerprints `.git/index`, `.git/config`,",
     "`.git/info/exclude`, `.git/HEAD` and every `.gitignore`, and reports a change as `test_changed_tree`.", "",
     "| Case | Archive | First round | This round | Broken failed | Fixed passed | Hidden on fixed | Hidden on broken + tests | hidden applicable / discriminates | integrity_control | broken_compiles | cache_control (applicable / passes / integrity; suite; hidden) | vs first round |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
same = 0
for c in cases:
    cid = c["case_id"]; o, f = old.get(cid, {}), one.get(cid, {}); records = new.get(cid, [])
    if not records: L.append(f"| {cid} | {o.get('verdict')} | {f.get('verdict')} | NOT RUN | | | | | | | | | no |"); continue
    r = records[-1]; h = r["hidden_control"]; i = r["integrity_control"]; cc = r.get("cache_control", {}); pc = r.get("prep_control", {})
    bad = sorted({(x.get("why") or x.get("outcome") or "?")[:200] for x in i["suite"] + i["hidden"] if x.get("outcome") != "sampled"})
    cache = "not applicable" if cc.get("applicable") is False else ("-" if cc.get("applicable") is None else
            f"yes / {cc.get('passes')} / {cc.get('integrity')}; {rc(cc.get('suite', []))}; {rc(cc.get('hidden', [])) if cc.get('hidden') else 'no hidden tests'}" + (f"; {cc['why'][:200]}" if cc.get("why") else ""))
    fh = f.get("hidden_control", {})
    ok = (r["verdict"], h["discriminates"], i["outcome"]) == (f.get("verdict"), fh.get("discriminates"), f.get("integrity_control", {}).get("outcome")); same += ok
    L.append(f"| {cid} | {o.get('verdict')} | {f.get('verdict')} (discriminates {fh.get('discriminates')}, integrity {f.get('integrity_control', {}).get('outcome')}) | **{r['verdict']}** | {r['broken_fail']}/{r['n']} | {r['fixed_pass']}/{r['n']} | "
             f"{rc(h['fixed']) if h['fixed'] else 'no hidden tests'} | {rc(h['broken_plus_tests']) if h['broken_plus_tests'] else 'no hidden tests'} | {h.get('applicable')} / {h['discriminates']} | {i['outcome']}{': ' + '; '.join(bad) if bad else ''} | {pc.get('broken_compiles')} | {cache} | {'same' if ok else 'DIFFERENT'} |")
    if len(records) > 1: L.append(f"| | | | ({len(records)} records for this case in this round's journal; the last is shown) | | | | | | | | | |")
L += ["", f"**Same verdict, `discriminates` and integrity outcome as the first round: {same} of {len(cases)}.** All 11 were `reproduced` in the archive.", "",
      "## Seconds per run (first run in a pod compiles from an empty build cache)", "", "| Case | First round: fixed runs | This round: broken runs | This round: fixed runs | This round: fix with the agent's cache (suite) |", "|---|---|---|---|---|"]
s = lambda runs: ", ".join(str(x.get("s")) for x in (runs or []))
for c in cases:
    cid = c["case_id"]; r = (new.get(cid) or [{}])[-1]
    L.append(f"| {cid} | {s(one.get(cid, {}).get('fixed', {}).get('runs'))} | {s(r.get('broken', {}).get('runs'))} | {s(r.get('fixed', {}).get('runs'))} | {s(r.get('cache_control', {}).get('suite'))} |")
(integ / "repro-compare.md").write_text("\n".join(L) + "\n"); print("\n".join(L[7:22]))
