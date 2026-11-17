#!/usr/bin/env python3
"""Runs ON aip-ci-01. For the smoke test only: writes <case>/failure.txt (the broken tree's output from our recorded
reproduction, the same text freeze.py writes for frozen cases) for cases with a "reproduced" verdict.
usage: smoke-failure.py <case-id>..."""
import json, sys
rep = {json.loads(l)["id"]: json.loads(l) for l in open("cases/repro.jsonl")}
for cid in sys.argv[1:]:
    r = rep[cid]; assert r["verdict"] == "reproduced", cid
    open(f"/srv/ci/cases/{cid}/failure.txt", "w").write(r["broken"].get("output_head", ""))
    print(cid, "failure.txt", len(r["broken"].get("output_head", "")), "chars")
