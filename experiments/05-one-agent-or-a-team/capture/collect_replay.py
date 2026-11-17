#!/usr/bin/env python3
"""Replays one repetition of the real collection log of experiment v06-team (collect-c1.log, copied from the lab VM;
here in report/collection/) as a time-lapse: same lines, same order, ~0.8 s per attempt instead of
~5 minutes. Each attempt line is reformatted into columns (task, setup, outcome, model calls, agent minutes, cost
rounded to the cent); the round's closing lines are printed verbatim. Nothing is invented: every value comes from the
log line it replaces. The validator column is left out on purpose: it is the verdict before the blind review.
Usage: collect_replay.py <collect-c1.log> <repetition> [seconds per line]"""
import re, sys, time
log, rep = open(sys.argv[1]).read().splitlines(), sys.argv[2]
step = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8
G, Y, D, B, R = "\033[32m", "\033[33m", "\033[90m", "\033[1m", "\033[0m"
start = max(i for i, l in enumerate(log) if l.startswith(f"== c1 repetition {rep} start"))
LINE = re.compile(r"c1-t(\d)-([ab])-r(\d)\S* agent: (\S+) tools \d+ calls (\d+) s ([\d.]+) \| gateway \$ ([\d.]+)")
for l in log[start:]:
    m = LINE.match(l)
    if m:
        t, cfg, r, out, calls, secs, usd = m.groups()
        oc = Y if out in ("budget_exhausted", "stopped_max_tokens") else ""
        print(f"  task {t}  {'one agent' if cfg == 'a' else 'team     '}  {oc}{out:<18}{R} {calls:>3} calls  {float(secs) / 60:4.1f} min  ${float(usd):.2f}")
    elif l.startswith("== ") or l.startswith("ROUND"):
        print((Y if "NOT started" in l else "" if l.startswith("ROUND") else D) + l + R)   # no bold green: OCR (highlights) cannot read it
    else:
        continue
    sys.stdout.flush(); time.sleep(step)
