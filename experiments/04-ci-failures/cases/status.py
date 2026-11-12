#!/usr/bin/env python3
"""One line: how many of the candidates are settled, and the verdict counts."""
import collections, itertools, json, os, re
rd = lambda p: [json.loads(l) for l in open(p)] if os.path.exists(p) else []
cands = rd("mining/candidates-go.jsonl") + rd("mining/candidates-python.jsonl")
cid = lambda c: re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
skip = set(open("cases/excluded-recheck.txt").read().split()) if os.path.exists("cases/excluded-recheck.txt") else set()
rep = {r["id"]: r["verdict"] for r in rd("cases/repro.jsonl")}
pf = set()
for l in (open("cases/prep-out/prep.jsonl") if os.path.exists("cases/prep-out/prep.jsonl") else []):
    m = re.search(r'"id": "([^"]+)", "prep": "fail"|PREP_FAIL ([^:]+):', l)
    if m: pf.add(m.group(1) or m.group(2))
ids = [cid(c) for c in cands if cid(c) not in skip]
settled = [i for i in ids if i in rep or i in pf]
print(f"settled {len(settled)}/{len(ids)} | " + ", ".join(f"{k} {v}" for k, v in collections.Counter(rep[i] for i in ids if i in rep).most_common()) + f" | prep failed {sum(i in pf and i not in rep for i in ids)}")
