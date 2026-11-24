#!/usr/bin/env python3
"""Runs ON aip-ctx-01. Builds the reproduction report of experiment 05 from what the lab recorded:
/srv/ci/secret/<T#>/meta.json (snapshot record), /srv/ci/secret/<T#>/cases.json (team_host.py derive) and the
validator controls in /srv/ci/validate/<T#>-{gold,empty}.json. Writes into --out DIR:
  repro-report.md   one table per question (usability, counts, times), per task
  tasks.csv         task id, n, original commit, snapshot hash, areas, #F2P, #P2P   (NOT frozen: the main session freezes)
  cases/<T#>.json   the per-case lists (same content as cases.json, indented)
No app source is written: test names, file paths, hashes and timings only."""
import csv, json, pathlib, statistics, sys

ROOT = pathlib.Path("/srv/ci")
out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]); (out / "cases").mkdir(parents=True, exist_ok=True)
tasks = sorted(p.name for p in (ROOT / "secret").iterdir() if (p / "meta.json").exists())
fmt = lambda xs: "/".join(f"{x:.0f}" for x in xs) if xs else "-"
med = lambda xs: round(statistics.median(xs), 1) if xs else None
rows, lines, timing, detail, stage_rows = [], [], [], [], []
def ctl(v):
    if not v: return "-"
    if "decided_in_stage" not in v: return f"{v.get('outcome')} (rule before E10: 3 samples of every job; {v.get('wall_s')} s)"
    extra = f", broken {len(v.get('broken', []))}, unstable in attempt {len(v.get('unstable_in_attempt', []))}, environment-dependent {len(v.get('environment_dependent', []))}" if v.get("stage2") else ""
    return f"{v.get('outcome')} (stage {v.get('decided_in_stage')}{extra}; {v.get('wall_s')} s)"
PERF = ("**No performance test is executed (criteria E9, owner's rule of 15/11).** How it was verified: (1) the jobs only run `flutter test` over "
        "`test/**/*_test.dart`, one Jest process per file of `functions/tests/*.test.js` and `functions/tests/e2e/*.test.js`, and the commit's own "
        "`tests/e2e-functions` file; no `make` target is called, `integration_test/` (the perf journeys [two app perf test files], "
        "[their baselines file]) and `test_driver/perf_driver.dart` are never passed to a runner, and "
        "`load-tests/` (k6) is not in any snapshot (E4). (2) The 8 snapshots were scanned on the VM for file names, test titles and elapsed-time code "
        "inside the trees the jobs read. One case exists whose purpose is to measure time: "
        "`test/redacted_timing_test.dart::Timing group timing case (name redacted)` [file and case names redacted for the public copy] (the app "
        "itself calls it a performance test and skips it on CI). It ran inside the Flutter suite before the rule arrived: in task 4's first area "
        "sample on each tree and in the exploratory single-process run of 18:07 (not used for any list). Since 19:14 UTC `executor/team.py` leaves it "
        "out of every `flutter test` by name (checked in a pod: the case does not start, its file's other cases do), and "
        "`team_host.classify` drops it from every list (`not_run_performance` in the case files). It was in no F2P or P2P list: none had been "
        "derived for a Flutter task yet. (3) Looked at and kept, because the time bound is the behaviour under test and nothing is measured for "
        "its own sake: one case of [an app test file] (a superseded wait must return before an 8 s window), two cases "
        "of [a functions test file] (a deadline must cut slow reads), the two other cases of the "
        "same file with 'timing'/'speed' in the title (order of awaits), and [an app test file] "
        "(a string helper). If the owner wants these out as well, they are five named cases and one file.")
for tid in tasks:
    sm = json.load(open(ROOT / "secret" / tid / "meta.json"))
    cf = ROOT / "secret" / tid / "cases.json"
    c = json.load(open(cf)) if cf.exists() else None
    if c: (out / "cases" / f"{tid}.json").write_text(json.dumps(c, indent=1, ensure_ascii=False))
    areas = ",".join(a for a, on in sm["areas_in_scope"].items() if on)
    n = c["counts"] if c else {}
    controls = {}
    for kind in ("gold", "empty"):
        f = ROOT / "validate" / f"{tid}-{kind}.json"
        if not f.exists(): f = ROOT / "validate" / f"{tid}-{kind}.before-E10.json"      # task 1's first controls, older rule
        if f.exists():
            v = json.load(open(f)); controls[kind] = v
    commit_s, area_s = [], {}
    if c:
        for name, j in c["jobs"].items():
            ts = [s["tool_s"] for s in j["samples"] if s.get("tool_s") is not None]
            pods = [s["pod_wall_s"] for s in j["samples"] if s.get("pod_wall_s") is not None]
            timing.append((tid, name, j["kind"], j["scope"], len(ts), med(ts), min(ts) if ts else None, max(ts) if ts else None, med(pods),
                           (j["samples"][0].get("limits") or {}) if j["samples"] else {}, j.get("counts") or {}))
            (commit_s if j["scope"] == "commit" else area_s.setdefault(j["area"], [])).append(med(ts) or 0)
    usable = "?" if not c else ("yes" if c["usable"] else "NO")
    g, e = controls.get("gold"), controls.get("empty")
    rows.append({"task": tid, "n": sm["n"], "commit": sm["commit"][:8], "snapshot_commit": sm["snapshot_commit"], "snapshot_tar_sha256": sm["snapshot_tar_sha256"],
                 "areas": areas, "f2p": n.get("f2p"), "p2p": n.get("p2p"), "excluded": n.get("excluded_fail_both"), "unstable": n.get("unstable"),
                 "usable": usable})
    lines.append(f"| {tid} | `{sm['commit'][:8]}` | `{sm['snapshot_commit'][:12]}` | `{sm['snapshot_tar_sha256'][:16]}` | {areas} | {n.get('f2p', '?')} | {n.get('p2p', '?')} | "
                 f"{n.get('excluded_fail_both', '?')} | {n.get('unstable', '?')} | {n.get('skipped', '?')} | {sum(commit_s):.0f} s | "
                 f"{', '.join(f'{a} {sum(v):.0f} s' for a, v in sorted(area_s.items())) or '-'} | {usable} | "
                 f"{ctl(g)} | {ctl(e)} |")
    # criteria E10: what one validation costs, from the gold-tree samples of the reproduction (median pod wall per job)
    if c:
        def cost(scope_commit):
            js = [(n, j) for n, j in c["jobs"].items() if (j["scope"] == "commit") == scope_commit and ((j.get("counts") or {}).get("f2p", 0) + (j.get("counts") or {}).get("p2p", 0)) > 0]
            rows_ = []
            for n, j in js:
                walls = [x["pod_wall_s"] for x in j["samples"] if x["tree"] == "gold" and x.get("pod_wall_s")]
                lim = next((x.get("limits") for x in j["samples"] if x.get("limits")), {}) or {}
                rows_.append((n, float(lim.get("cpu", 0) or 0), float(str(lim.get("memory", "0Gi")).replace("Gi", "")) + 2, med(walls) or 0))
            return rows_
        s1, s2 = cost(True), cost(False)
        stage_rows.append((tid, s1, s2, g, e))
    if c:
        extra = {k: c["counts"].get(k) for k in ("broken_by_gold", "fixed_outside_commit_tests", "commit_tests_pass_both_out_of_scope")}
        extra["not_run_performance"] = [(e["case"], f"in {e['present_in_samples']} early samples") for e in c.get("not_run_performance", [])]
        detail.append(f"### {tid}\n- problems: {c['problems'] or 'none'}\n- other counts: {extra}\n"
                      + "".join(f"- unstable: `{u['case']}` baseline {u['baseline']} gold {u['gold']}\n" for u in c["unstable"][:25])
                      + "".join(f"- passes on baseline, FAILS with the owner's fix: `{u['case']}`\n" for u in c["broken_by_gold"][:25])
                      + "".join(f"- fixed by the owner's fix but outside the commit's test files: `{u['case']}`\n" for u in c["fixed_outside_commit_tests"][:25])
                      + f"- files that failed to load on gold: {sum(len(j.get('file_errors_gold', [])) for j in c['jobs'].values())}"
                      + "".join(f"\n  - {name}: {', '.join(j.get('file_errors_gold', [])[:12])}" for name, j in c["jobs"].items() if j.get("file_errors_gold")) + "\n")
md = ["# Reproduction report · experiment 05 (A-v07) · generated on the VM", "",
      "Private (file paths and test names of the app). Counts are test CASES; every sample is a fresh no-network Kata pod.",
      "F2P = commit test files, fails 3/3 on the snapshot and passes 3/3 with the owner's fix. P2P = suites of the areas the commit touches, passes 3/3 on both.",
      "Times are the median tool time of one sample (sum over the task's jobs of that kind); pod start, copy and network gate add about 35 to 60 s per pod.", "",
      PERF, "",
      "| Task | Commit | Snapshot commit | Snapshot tar sha256 | Areas in scope | F2P | P2P | Excluded (fails on both) | Unstable | Skipped | Commit tests | Area suites | Usable | Control: owner's fix | Control: empty patch |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|", *lines, "",
      "## Time per job (tool seconds over the samples of both trees)", "",
      "| Task | Job | Kind | Scope | Samples | Median | Min | Max | Median pod wall | CPU / memory limit | Cases F2P / P2P / excluded / unstable |", "|---|---|---|---|---|---|---|---|---|---|---|"]
for tid, name, kind, scope, k, m, lo, hi, podm, lim, cnt in timing:
    md.append(f"| {tid} | {name} | {kind} | {scope} | {k} | {m} | {lo} | {hi} | {podm} | {lim.get('cpu', '-')} / {lim.get('memory', '-')} | "
              f"{cnt.get('f2p', '-')} / {cnt.get('p2p', '-')} / {cnt.get('excluded_fail_both', '-')} / {cnt.get('unstable', '-')} |")
md += ["", "## What one validation costs (criteria E10: two stages)", "",
       "Stage 1 = the commit jobs that hold listed cases, 3 samples each. Stage 2 = one sample of each area job (plus two reruns of the files with a "
       "P2P case that did not pass, only when that happens: not included below). Per pod: CPU limit and VM memory (limit + 2 GiB, what the ledger "
       "counts); time = median pod wall of the gold-tree samples of the reproduction, taken on the 8-vCPU VM with the queue keeping it full, so "
       "they are upper-side figures. 'All at once' = wall time if every pod of the stage can start together (needs the CPUs and memory shown).",
       "", "| Task | Stage 1: pods | Stage 1: CPUs / GiB all at once | Stage 1: CPU-min | Stage 1: wall all at once | Stage 2: pods | Stage 2: CPUs / GiB all at once | "
       "Stage 2: CPU-min | Stage 2: wall all at once | Measured, owner's fix control (stage 1 / stage 2 wall, 3 pods at a time on 8 vCPUs) | Measured, empty patch (stage 1 wall) |",
       "|---|---|---|---|---|---|---|---|---|---|---|"]
tot1 = tot2 = 0.0
for tid, s1, s2, g, e in stage_rows:
    c1 = sum(cpu * w * 3 for _, cpu, _, w in s1) / 60; c2 = sum(cpu * w for _, cpu, _, w in s2) / 60; tot1 += c1; tot2 += c2
    meas = lambda v, k: (v or {}).get(k, {}).get("wall_s", "-") if isinstance((v or {}).get(k), dict) else "-"
    md.append(f"| {tid} | {3 * len(s1)} ({', '.join(n for n, *_ in s1)}) | {sum(cpu for _, cpu, _, _ in s1) * 3:.0f} / {sum(m for _, _, m, _ in s1) * 3:.0f} | {c1:.0f} | "
              f"{max([w for *_, w in s1] or [0]):.0f} s | {len(s2)} ({', '.join(n for n, *_ in s2) or '-'}) | {sum(cpu for _, cpu, _, _ in s2):.0f} / {sum(m for _, _, m, _ in s2):.0f} | "
              f"{c2:.0f} | {max([w for *_, w in s2] or [0]):.0f} s | {meas(g, 'stage1')} s / {meas(g, 'stage2')} s | {meas(e, 'stage1')} s |")
md += ["", f"Sum over the 8 tasks, one validation each: stage 1 {tot1:.0f} CPU-min, stage 2 {tot2:.0f} CPU-min. "
       f"48 attempts = 6 per task: at most {6 * tot1 / 60:.1f} CPU-hours of stage 1 (always run) and {6 * tot2 / 60:.1f} CPU-hours of stage 2 "
       f"(only for attempts that pass stage 1), before reruns.", ""]
md += ["", "## Per task detail", "", *detail]
(out / "repro-report.md").write_text("\n".join(md) + "\n")
with open(out / "tasks.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"wrote {out}/repro-report.md, tasks.csv and {len(tasks)} case files")
