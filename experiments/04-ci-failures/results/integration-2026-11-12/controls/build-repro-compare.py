#!/usr/bin/env python3
"""Integration (2026-11-12), runs on our own files. Compares the reproduction of the 11 frozen cases on the fresh cluster
(integration/repro/repro.jsonl, new preparation and controls) with the archived records (cases/repro.jsonl, read only).
usage: build-repro-compare.py <experiment-dir> <integration-dir>"""
import csv, json, pathlib, sys
exp, integ = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
cases = list(csv.DictReader(open(exp / "cases" / "cases.csv")))
old = {}
for l in open(exp / "cases" / "repro.jsonl"):
    r = json.loads(l); old[r["id"]] = r                       # the last record of a case is the one that counted
new = {}
for l in open(integ / "repro" / "repro.jsonl"):
    r = json.loads(l); new.setdefault(r["id"], []).append(r)
rc = lambda runs: "/".join("pass" if x.get("rc") == 0 else ("timeout" if x.get("rc") == 124 else "fail") for x in runs) or "-"
L = ["# Reproduction of the 11 frozen cases on the fresh cluster (2026-11-12) vs the archive", "",
     "New preparation (per-case pods in `ci-prep`, private fixed-tree Go cache) and new controls (`hidden_control`, `integrity_control`).",
     "Archive: all 11 `reproduced` (broken 3/3 fail, fixed 3/3 pass; the archived harness had no hidden or integrity control).",
     "`hidden_control`: the maintainer's test changes on the fixed tree (3 runs) and on the broken tree plus only those test changes (3 runs);",
     "`discriminates` = all fixed runs pass and all broken-plus-tests runs fail. Nothing was excluded or fixed on the basis of this table.", "",
     "| Case | Archived verdict | New verdict | Broken failed | Fixed passed | Hidden on fixed (3) | Hidden on broken + tests (3) | discriminates | integrity_control | Same verdict? |",
     "|---|---|---|---|---|---|---|---|---|---|"]
same = 0
for c in cases:
    cid = c["case_id"]; o = old.get(cid, {}); records = new.get(cid, [])
    if not records: L.append(f"| {cid} | {o.get('verdict')} | NOT RUN | | | | | | | no |"); continue
    r = records[-1]; h = r["hidden_control"]; i = r["integrity_control"]
    ok = r["verdict"] == o.get("verdict"); same += ok
    has_hidden = bool(h["fixed"] or h["broken_plus_tests"])     # from the fresh run: the current TESTFILE pattern decides
    note = "" if has_hidden == (c["hidden_tests"] == "yes") else " (archive: no hidden tests for this case)"
    integ_text = i["outcome"] + ("" if i["outcome"] == "clean" else ": " + "; ".join(sorted({(x.get("why") or x.get("outcome") or "?")[:120] for x in i["suite"] + i["hidden"] if x.get("outcome") != "sampled"})))
    L.append(f"| {cid} | {o.get('verdict')} ({o.get('broken_fail')}/{o.get('n')} fail, {o.get('fixed_pass')}/{o.get('n')} pass) | **{r['verdict']}** | {r['broken_fail']}/{r['n']} | {r['fixed_pass']}/{r['n']} | "
             f"{rc(h['fixed']) + note if has_hidden else 'no hidden tests'} | {rc(h['broken_plus_tests']) if has_hidden else 'no hidden tests'} | {h['discriminates'] if has_hidden else 'n/a (false)'} | {integ_text} | {'same' if ok else 'DIFFERENT'} |")
    if len(records) > 1: L.append(f"| | | ({len(records)} records for this case in the fresh run; the last one is shown) | | | | | | | |")
L += ["", f"**Same verdict as the archive: {same} of {len(cases)}.**", "",
      "## Timing of the first run in a fresh pod (seconds; Go compiles from an empty build cache)", "",
      "| Case | Archive: broken runs | New: broken runs | New: fixed runs |", "|---|---|---|---|"]
for c in cases:
    cid = c["case_id"]; o = old.get(cid, {}); r = (new.get(cid) or [{}])[-1]
    s = lambda rec: ", ".join(str(x.get("s")) for x in (rec or {}).get("runs", []))
    L.append(f"| {cid} | {s(o.get('broken'))} | {s(r.get('broken'))} | {s(r.get('fixed'))} |")
(integ / "repro-compare.md").write_text("\n".join(L) + "\n"); print("\n".join(L))
