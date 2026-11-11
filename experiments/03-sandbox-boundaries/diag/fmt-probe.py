#!/usr/bin/env python3
"""Reads probe JSON lines on stdin and prints one readable line per probe, as they arrive."""
import json, sys
for l in sys.stdin:
    r = json.loads(l); print(f"{r['probe']:18} {r['result']}", flush=True)
