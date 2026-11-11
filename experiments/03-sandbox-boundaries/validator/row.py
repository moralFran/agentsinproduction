#!/usr/bin/env python3
"""row.py <label> <validation-json> <out.jsonl>: appends one row and prints a short summary (reasons on their own lines)."""
import json, sys
label, v, out = sys.argv[1], json.loads(sys.argv[2] or '{"valid": null, "reasons": ["no validation output"]}'), sys.argv[3]
open(out, "a").write(json.dumps({"patch": label, **v}) + "\n")
print(f"{label.rsplit('/', 1)[-1]:27} valid={str(v.get('valid')):5} passed={v.get('passed')} skipped={v.get('skipped')} failed={v.get('failed')}")
for r in v.get("reasons", []): print(f"    · {r[:68]}")
