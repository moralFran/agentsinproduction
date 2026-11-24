#!/usr/bin/env python3
"""Short terminal anchors for A-v08, computed live from experiment 06's report files (report/v1-live.json,
report/v1-calls.csv, report/c1-replays.jsonl; run it from report/: `python3 ../capture/show_results.py live`). No number is typed here: every
value is read or summed from those files. Cost parts use the lab gateway's prices (Sonnet 5.5: US$ 2 / 10 per million
tokens, cache writes 1.25x, or 2x with the 1-hour lifetime, cache reads 0.05x), and the script checks that the parts add
up to what the gateway booked. Numbers only: no command text, no paths, no app content.
Usage: show_results.py live | split | replays"""
import csv, json, sys
mode = sys.argv[1]
G, R, Y, D, Z = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
live = json.load(open("v1-live.json"))
name = {"L0": "no compaction", "L2": "compacted"}
def label(x):
    return f"{name[x['condition']]} r{x['run'].split('-r')[1][0]}"
order = sorted(live, key=lambda x: (x["condition"], x["run"].replace("-t2", "")))
if mode == "live":
    print(f"{'attempt':<18}{'ended':<14}{'my tests':<11}{'min':>5}{'US$':>7}{'calls':>7}{'largest prompt':>16}{'from cache':>12}")
    for x in order:
        ended = {"finished": "finished", "timeout": "40-min clock", "budget_exhausted": "budget cap"}[x["outcome"]]
        tests = G + "passed  " + Z if x["validator"] == "resolved" else D + "rejected" + Z
        col = G if x["outcome"] == "finished" else Y
        print(f"{label(x):<18}{col}{ended:<14}{Z}{tests}   {x['minutes']:>5.1f}{x['usd_gateway']:>7.2f}{x['model_calls']:>7}{x['largest_prompt']:>16,}{100 * x['cache_read_share']:>11.1f}%")
elif mode == "split":
    rows = list(csv.DictReader(open("v1-calls.csv")))
    print(f"{'attempt':<18}{'read from cache':>17}{'written':>9}{'output':>8}{'total':>8}{'  cache read, of the bill':>26}")
    for x in order:
        cs = [c for c in rows if c["run"] == x["run"]]
        s = lambda k: sum(int(c[k]) for c in cs)
        rd, wr, out, plain = s("cr") * 0.10 / 1e6, s("cw") * 2.50 / 1e6, s("out") * 10 / 1e6, s("in") * 2 / 1e6
        tot = rd + wr + out + plain
        assert abs(tot - x["usd_gateway"]) < 0.01
        col = R if rd / tot > 0.5 else Y
        print(f"{label(x):<18}{col}{rd:>17.2f}{Z}{wr:>9.2f}{out:>8.2f}{tot:>8.2f}{col}{100 * rd / tot:>25.0f}%{Z}")
elif mode == "replays":
    reps = [json.loads(l) for l in open("c1-replays.jsonl") if l.strip()]
    runs = {}
    for r in reps:
        if "k" in r: runs.setdefault(r["cond"], []).append(r)
    base = sum(r["usd"] for r in runs["R0"])
    desc = {"R0": "control: nothing changed", "R1": "time line in the system prompt", "R2": "tool order swapped",
            "R3": "effort changed mid-session", "R4": "three 6-min pauses (simulated)", "R4-1h": "fix: pauses, one-hour lifetime",
            "R5": "old reminder deleted", "R5-sys": "fix: reminder kept + system msg"}
    print(f"{'replay of the same 20 requests':<34}{'US$':>8}{'× control':>11}{'from cache':>12}")
    for k, c in enumerate(("R0", "R1", "R4", "R2", "R3", "R5", "R4-1h", "R5-sys")):
        if k == 6: print()
        rs = runs[c]; usd = sum(r["usd"] for r in rs); cr = sum(r["cr"] for r in rs)
        tot = cr + sum(r["cw"] + r["in"] for r in rs)
        col = R if usd / base >= 2 else Y if usd / base >= 1.15 else G
        print(f"{desc[c]:<34}{usd:>8.4f}{col}{usd / base:>10.1f}×{Z}{100 * cr / tot:>11.1f}%")
