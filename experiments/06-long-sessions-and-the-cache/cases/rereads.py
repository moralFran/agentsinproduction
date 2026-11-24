#!/usr/bin/env python3
"""Re-reads of an attempt (experiment 06, criteria E5; fixed before the first live attempt, 23/11/2026).
A re-read = a command that READS a file which the same attempt already read and has not touched since.
  read     a command whose program is cat, head, tail, sed -n, nl, less, more or bat, naming the file (its last path
           argument that is not an option); several files in one cat are several reads
  neutral  grep, rg, wc, ls, find, stat, file, and git diff/status/log/show: they neither read (by this rule) nor touch
  touched  any other command that names the file (an editor, a redirect, sed -i, git apply, a script...): the file may
           have changed, so its next read is a first read again. Conservative: it can only lower the count.
Paths are compared as written, after dropping a leading "./". Commands joined with && ; | are split first.
usage: rereads.py <attempts.jsonl> [--run <id>]   prints per run: reads, re-reads, re-reads after a compaction"""
import json, re, shlex, sys

READERS = {"cat", "head", "tail", "nl", "less", "more", "bat"}
NEUTRAL = {"grep", "egrep", "fgrep", "rg", "wc", "ls", "find", "stat", "file"}

def neutral(part):
    try: w = shlex.split(part)
    except ValueError: return False
    if not w or any(c in part for c in (">", "<<")): return False
    prog = w[0].rsplit("/", 1)[-1]
    return prog in NEUTRAL or (prog == "git" and len(w) > 1 and w[1] in ("diff", "status", "log", "show"))

def parts(cmd):
    return [p.strip() for p in re.split(r"&&|\|\||;|\|", cmd) if p.strip()]

def reads_in(part):
    """Files this command part reads, or None if it is not a read."""
    try: w = shlex.split(part)
    except ValueError: return None
    if not w: return None
    prog = w[0].rsplit("/", 1)[-1]
    if prog == "sed" and "-n" in w and not any(x.startswith("-i") for x in w): files = [x for x in w[1:] if not x.startswith("-") and not re.match(r"^[\d,]*[pP]?$", x) and not x.endswith("p")]
    elif prog in READERS and not any(c in part for c in (">", "<<")): files = [x for x in w[1:] if not x.startswith("-") and not x.isdigit()]
    else: return None
    return [f[2:] if f.startswith("./") else f for f in files]

def count(commands, compactions_at=()):
    seen, n_reads, rereads, after_compact = set(), 0, 0, 0
    for c in commands:
        for p in parts(c["cmd"]):
            if neutral(p): continue
            r = reads_in(p)
            if r is None:                       # touched: forget every file it names
                seen = {f for f in seen if f not in p}
                continue
            for f in r:
                n_reads += 1
                if f in seen:
                    rereads += 1
                    if any(c.get("call", 0) > a for a in compactions_at): after_compact += 1
                seen.add(f)
    return n_reads, rereads, after_compact

if __name__ == "__main__":
    want = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else None
    for line in open(sys.argv[1]):
        row = json.loads(line); a = row.get("agent") or {}
        if not a or (want and row.get("run") != want): continue
        r, rr, ac = count(a.get("commands", []), [c["at_call"] for c in a.get("compactions", [])])
        print(json.dumps({"run": row.get("run"), "condition": row.get("config"), "reads": r, "rereads": rr, "rereads_after_a_compaction": ac}))
