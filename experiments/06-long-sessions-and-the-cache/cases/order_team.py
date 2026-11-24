#!/usr/bin/env python3
"""
Order of the attempts of experiment 05 (one agent vs a team), fixed before the collection.

  order_team.py <tasks.csv> <order.csv> [--seed N] [--reps 3]

Design: every repetition is one block holding each (task, configuration) cell once; the cells of a block are shuffled
with random.Random(f"{seed}:{rep}"). So both configurations of a task run in the same block (same day, same state of
the machine), neither configuration always goes first, and repetition r+1 starts only after repetition r is complete.
The seed is written in the file's first line and in criteria.md before any attempt runs. The same inputs always give
the same file (checked by running it twice).
"""
import csv, hashlib, random, sys

CONFIGS = ("A", "B")          # A = one agent, B = orchestrator + subagents per area + reviewer


def task_ids(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    col = next((c for c in ("task", "id", "task_id") if rows and c in rows[0]), None)
    if col is None: sys.exit(f"{path}: no task/id column")
    ids = [r[col].strip() for r in rows if r[col].strip()]
    if len(ids) != len(set(ids)): sys.exit(f"{path}: repeated task ids")
    return ids


def build(ids, seed, reps):
    out = []
    for rep in range(1, reps + 1):
        cells = [(t, c) for t in sorted(ids) for c in CONFIGS]
        random.Random(f"{seed}:{rep}").shuffle(cells)
        out += [(rep, t, c) for t, c in cells]
    return out


def main():
    a = sys.argv[1:]
    seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 20261115
    reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 3
    src, dst = a[0], a[1]
    ids = task_ids(src)
    rows = build(ids, seed, reps)
    assert rows == build(ids, seed, reps)
    with open(dst, "w", newline="") as f:
        f.write(f"# seed={seed} reps={reps} tasks={len(ids)} tasks_sha256={hashlib.sha256(open(src, 'rb').read()).hexdigest()[:16]}\n")
        w = csv.writer(f, lineterminator="\n"); w.writerow(["pos", "rep", "task", "config", "attempt"])
        for i, (rep, t, c) in enumerate(rows, 1): w.writerow([i, rep, t, c, f"{t}-{c}-r{rep}"])
    first = sum(1 for i in range(0, len(rows), 1) if rows[i][2] == "A" and not any(r[:2] == rows[i][:2] for r in rows[:i]))
    print(f"{dst}: {len(rows)} attempts, seed {seed}; configuration A runs before B in {first} of {len(ids) * reps} task×repetition pairs")


if __name__ == "__main__":
    main()
