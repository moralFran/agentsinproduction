#!/usr/bin/env python3
"""Runs ON aip-ci-01. The numbers of a round of experiment 05, from the journal only (results/attempts-<round>.jsonl):
a CSV with one line per attempt, then totals per configuration, then one line per task. No app code, path or name.
The patch size is left out unless --with-sizes is given: each blind packet shows its patch, so size next to
configuration would map packets to configurations (use the flag only after the key has been opened).
Notes on two columns: tool_calls counts every bash command of any agent AND every dispatch/review call of the
orchestrator; tool_errors counts every command that exited non-zero, a grep with no match included.
  usage: summary_team.py <round-id> [--with-sizes]        (report/<round>-attempts.csv is the first block of the output)"""
import sys
rnd = sys.argv[1]; SIZES = "--with-sizes" in sys.argv
import json, collections, statistics as st
rows=[json.loads(l) for l in open(f"results/attempts-{rnd}.jsonl")]
def share(a): 
    t=a["in_tok"]+a["cache_write"]+a["cache_read"]; return a["cache_read"]/t if t else 0
print("run,case,config,rep,agent_outcome,validator,usd,model_calls,tool_calls,tool_errors,in_tok,cache_write,cache_read,out_tok,cache_read_share,agent_s,attempt_wall_s,validator_wall_s,roles,dispatches,reviews" + (",patch_bytes" if SIZES else ""))
for r in sorted(rows, key=lambda r:(r["case"],r["config"],r["rep"])):
    a=r["agent"]; v=r["validator"]
    print(",".join(str(x) for x in [r["run"],r["case"],r["config"],r["rep"],a["outcome"],v["outcome"],round(r["gateway"]["spent_usd"],4),a["model_calls"],a["tool_calls"],a.get("tool_errors"),a["in_tok"],a["cache_write"],a["cache_read"],a["out_tok"],round(share(a),3),a["total_s"],r["wall_s"],v["wall_s"],len(a.get("roles",[])),len(a.get("dispatches",[])),a.get("reviews")] + ([a.get("patch_bytes")] if SIZES else [])))
print()
for c in "AB":
    rs=[r for r in rows if r["config"]==c]; ok=[r for r in rs if r["validator"]["outcome"]=="resolved"]
    tot=lambda k: sum(r["agent"][k] for r in rs)
    usd=sum(r["gateway"]["spent_usd"] for r in rs)
    inp=tot("in_tok")+tot("cache_write")+tot("cache_read")
    print(c, "attempts", len(rs), "passed", len(ok), "usd", round(usd,4), "usd/passed", round(usd/len(ok),4), "usd of passed only", round(sum(r["gateway"]["spent_usd"] for r in ok),4),
          "| calls", tot("model_calls"), "tools", tot("tool_calls"), "tool_errors", tot("tool_errors"),
          "| input", inp, "cache_read", tot("cache_read"), "share", round(tot("cache_read")/inp,4), "cache_write", tot("cache_write"), "uncached", tot("in_tok"), "out", tot("out_tok"),
          "| agent_s total", round(sum(r["agent"]["total_s"] for r in rs)), "median", round(st.median(r["agent"]["total_s"] for r in rs)), "agent_s/passed", round(sum(r["agent"]["total_s"] for r in rs)/len(ok)),
          "| role counts", sorted(collections.Counter(len(r["agent"].get("roles",[])) for r in rs).items()), "dispatches", sorted(collections.Counter(len(r["agent"].get("dispatches",[])) for r in rs).items()))
# per task: A vs B usd and time (mean over the 2 reps), passes
print()
for t in sorted({r["case"] for r in rows}):
    out=[t]
    for c in "AB":
        rs=[r for r in rows if r["case"]==t and r["config"]==c]
        out += [c, f'pass {sum(r["validator"]["outcome"]=="resolved" for r in rs)}/{len(rs)}', f'usd {" ".join(str(round(r["gateway"]["spent_usd"],3)) for r in sorted(rs,key=lambda r:r["rep"]))}', f's {" ".join(str(round(r["agent"]["total_s"])) for r in sorted(rs,key=lambda r:r["rep"]))}']
    print(" | ".join(out))
# roles in team attempts
rc=collections.Counter()
for r in rows:
    if r["config"]=="B":
        for ro in r["agent"].get("roles",[]): rc[ro["role"]]+=1
print("\nteam roles used across the 16 attempts:", dict(rc))
