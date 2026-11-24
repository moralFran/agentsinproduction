#!/usr/bin/env python3
"""Runs ON aip-ctx-01 (experiment 06, criteria E5). Numbers of the live round only: no command text, no paths, no
summaries, no app content, so both outputs can leave the VM.
  report/<round>-calls.csv     one line per model call: run, condition, n, role, prompt, uncached input, cache write,
                               cache read, output tokens, US$ (Sonnet 5.5 list prices, the same at every prompt length:
                               US$ 2 / 10 per million, cache write 1.25x, cache read US$ 0.10), seconds since the start
  report/<round>-live.json     per attempt: outcome, validator verdict, calls, tools, tool errors, minutes, US$ booked by
                               the gateway, largest prompt, compactions (call, prompt before, summary size), re-reads
                               (cases/rereads.py, the rule fixed before the first attempt) and, for each compaction, the
                               tool errors (exit code != 0) of the commands of the 20 model calls before and the 20 after
usage: live_report.py <round>"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rereads

PRICE = {"in": 2.0, "w5": 2.5, "r": 0.10, "out": 10.0}          # US$ per million tokens; Sonnet 5.5 has no long-prompt tier

def usd(c):
    p = PRICE
    return (c["in"] * p["in"] + c["cw"] * p["w5"] + c["cr"] * p["r"] + c["out"] * p["out"]) / 1e6

rnd = sys.argv[1]
rows = [json.loads(l) for l in open(f"results/attempts-{rnd}.jsonl") if l.strip()]
os.makedirs("report", exist_ok=True)
live = []
with open(f"report/{rnd}-calls.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["run", "condition", "n", "role", "prompt", "in", "cw", "cr", "out", "usd", "t"])
    for r in rows:
        a = r["agent"]
        for c in a["calls"]:
            w.writerow([r["run"], r["config"], c["n"], c["role"], c["prompt"], c["in"], c["cw"], c["cr"], c["out"], round(usd(c), 6), c["t"]])
        cmds = a.get("commands", [])
        def errs(lo, hi): return sum(1 for x in cmds if lo < x.get("call", 0) <= hi and x.get("rc", 0) != 0)
        def n_cmds(lo, hi): return sum(1 for x in cmds if lo < x.get("call", 0) <= hi)
        comp = [{"at_call": k["at_call"], "prompt_before": k["prompt_before"], "summary_chars": k["summary_chars"],
                 "errors_20_before": errs(k["at_call"] - 21, k["at_call"] - 1), "commands_20_before": n_cmds(k["at_call"] - 21, k["at_call"] - 1),
                 "errors_20_after": errs(k["at_call"], k["at_call"] + 20), "commands_20_after": n_cmds(k["at_call"], k["at_call"] + 20)}
                for k in a.get("compactions", [])]
        reads, rr, rr_after = rereads.count(cmds, [k["at_call"] for k in a.get("compactions", [])])
        v = r.get("validator") or {}
        live.append({"run": r["run"], "condition": r["config"], "outcome": a["outcome"], "validator": v.get("outcome"),
                     "validator_why": "touches a scratch test file" if "scratch" in str(v.get("why", "")) else ("" if v.get("outcome") == "resolved" else str(v.get("why", ""))[:60]),
                     "phases_ended": len(a.get("phases", [])), "reviewed": a.get("reviews", 0) > 0,
                     "model_calls": a["model_calls"], "tool_calls": a["tool_calls"], "tool_errors": a["tool_errors"],
                     "minutes": round(a["total_s"] / 60, 1), "usd_gateway": round(r["gateway"]["spent_usd"], 4),
                     "usd_list_price": round(sum(usd(c) for c in a["calls"]), 4),
                     "largest_prompt": max(c["prompt"] for c in a["calls"]),
                     "cache_read_share": round(a["cache_read"] / max(1, a["cache_read"] + a["cache_write"] + a["in_tok"]), 4),
                     "output_tokens": a["out_tok"], "compactions": comp,
                     "reads": reads, "rereads": rr, "rereads_after_a_compaction": rr_after})
json.dump(live, open(f"report/{rnd}-live.json", "w"), indent=1)
for x in live:
    print(x["run"], x["condition"], x["outcome"], x["validator"], "| $", x["usd_gateway"], "list", x["usd_list_price"], "| min", x["minutes"], "| prompt", x["largest_prompt"],
          "| rereads", x["rereads"], "/", x["reads"], "| compactions", [(k["at_call"], f'{k["errors_20_before"]}/{k["commands_20_before"]}', f'{k["errors_20_after"]}/{k["commands_20_after"]}') for k in x["compactions"]])
