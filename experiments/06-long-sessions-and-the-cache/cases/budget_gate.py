#!/usr/bin/env python3
"""
Budget gate of the collection (criteria.md E19), called by cases/run_team.sh from the experiment's folder.

  budget_gate.py missing <rep> <round> <cap> <margin>          -> how many attempts of the repetition are not in the journal
  budget_gate.py decide  <rep> <round> <cap> <margin> < state  -> go | resume | stop: <why>      (state = gateway GET /state)
  budget_gate.py end     <rep> <round> <cap> <margin> < state  -> writes the end record of the repetition

Rule: repetition 1 starts only if (attempts in a repetition) x cap fits in what is left of the gateway's total budget.
Repetition r >= 2 starts only if what is left >= margin x the cost of the most expensive complete repetition, where the
cost of a repetition = gateway spent at its end - gateway spent at its start (tries that never became an attempt
included). A halted gateway never starts a repetition. A repetition that already has a start record is resumed without
a new decision: the decision is made once, before its first attempt. Records go to results/budget-<round>.jsonl.
"""
import csv, json, os, sys, time


def order_rows():
    return list(csv.DictReader(l for l in open("order.csv") if not l.startswith("#")))


def journal(rnd):
    p = f"results/attempts-{rnd}.jsonl"
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def missing(rep, rnd):
    want = {r["attempt"] for r in order_rows() if int(r["rep"]) == rep}
    got = {f'{r["case"]}-{r["config"]}-r{r["rep"]}' for r in journal(rnd)}
    return sorted(want - got)


def records(rnd):
    p = f"results/budget-{rnd}.jsonl"
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def write(rnd, rec):
    with open(f"results/budget-{rnd}.jsonl", "a") as f:
        f.write(json.dumps(rec | {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n"); f.flush(); os.fsync(f.fileno())


def rep_costs(recs):
    """{rep: cost} for repetitions with both a start and an end record (the first start counts: a resume keeps it)."""
    start, end = {}, {}
    for r in recs:
        if r["event"] == "start": start.setdefault(r["rep"], r["spent_usd"])
        elif r["event"] == "end": end[r["rep"]] = r["spent_usd"]
    return {k: round(end[k] - start[k], 6) for k in end if k in start}


def decide(rep, cap, margin, state, recs, per_rep):
    """Returns (verdict, record or None). Pure: the caller writes the record."""
    if state.get("halted"): return f"stop: the gateway is halted ({state['halted']})", None
    left = round(state["budget_usd"] - state["spent_usd"] - state.get("reserved_usd", 0.0), 6)
    base = {"rep": rep, "spent_usd": state["spent_usd"], "left_usd": left, "cap_usd": cap, "margin": margin}
    if any(r["event"] == "start" and r["rep"] == rep for r in recs): return "resume", None
    if rep == 1:
        need = round(per_rep * cap, 6)
    else:
        costs = rep_costs(recs)
        if any(r not in costs for r in range(1, rep)):
            return f"stop: repetition {rep} cannot start before every earlier repetition has an end record", None
        need = round(margin * max(costs.values()), 6)
    if left + 1e-9 < need:
        why = f"stop: US$ {left:.4f} left, repetition {rep} needs US$ {need:.4f}"
        return why, base | {"event": "not_started", "need_usd": need}
    return "go", base | {"event": "start", "need_usd": need}


def main():
    action, rep, rnd, cap, margin = sys.argv[1], int(sys.argv[2]), sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
    if action == "missing":
        print(len(missing(rep, rnd))); return
    state = json.load(sys.stdin)
    if action == "decide":
        per_rep = sum(1 for r in order_rows() if int(r["rep"]) == rep)
        verdict, rec = decide(rep, cap, margin, state, records(rnd), per_rep)
        if rec: write(rnd, rec)
        print(verdict)
    elif action == "end":
        recs = records(rnd)
        if not any(r["event"] == "end" and r["rep"] == rep for r in recs):
            start = next((r["spent_usd"] for r in recs if r["event"] == "start" and r["rep"] == rep), None)
            write(rnd, {"rep": rep, "event": "end", "spent_usd": state["spent_usd"],
                        "cost_usd": None if start is None else round(state["spent_usd"] - start, 6)})
    else:
        sys.exit("unknown action")


if __name__ == "__main__":
    main()
