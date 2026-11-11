#!/usr/bin/env python3
"""The shell commands one recorded attempt ran, in order, and how it ended.   usage: show.py <task.jsonl> <run-id>"""
import json, sys
for l in open(sys.argv[1]):
    r = json.loads(l); a = r["agent"]
    if a.get("run", r.get("run")) != sys.argv[2]: continue
    for n, c in enumerate(a.get("commands", []), 1):
        cmd = " ".join(c["cmd"].split())
        print(f"{n}. $ {cmd[:66] + ('…' if len(cmd) > 66 else '')}\n     exit {c['rc']} · {c['s']:.2f} s")
    print(f"{a.get('outcome')} · {a.get('model_calls')} model calls · {a.get('total_s', 0):.1f} s · patch valid: {r['validation'].get('valid')}")
