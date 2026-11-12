#!/usr/bin/env python3
"""Picks the agent's report out of a pod log (stdin) and prints it as one JSON line.   usage: result.py <nonce>
The runner made the nonce and gave it to the harness only. The report is the LAST line `RESULT <nonce> <json object>`;
any other line that starts with RESULT is counted in `report_lines_rejected` and otherwise ignored. No such line: the
attempt has no result. The nonce shows which line the harness wrote; it does not make the content true (agent.py)."""
import json, sys

def pick(log, nonce):
    prefix, last, rejected = f"RESULT {nonce} ", None, 0
    for line in log.splitlines():
        if not line.startswith("RESULT"): continue
        obj = None
        if nonce and line.startswith(prefix):
            try: obj = json.loads(line[len(prefix):])
            except ValueError: pass
        if isinstance(obj, dict): last = obj
        else: rejected += 1
    r = last if last is not None else {"outcome": "no_result", "patch": ""}
    r["report_lines_rejected"] = rejected
    return r

if __name__ == "__main__":
    print(json.dumps(pick(sys.stdin.read(), sys.argv[1])))
