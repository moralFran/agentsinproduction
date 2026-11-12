#!/usr/bin/env python3
"""Rebuilds cases/prep-out/prep.jsonl after it was truncated by a crash of reset-case.sh (11/11 21:33 UTC: the old
version opened the file for writing before parsing it). Sources: every case with a meta.json (preparation ok) and the
"prep failed" lines the workers printed in their logs. Keeps the lines written after the crash."""
import glob, json, os, re
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
RESET = {"openbyteinc-quantdinger-733f7bc7", "lexiforest-curl-cffi-cfe2d555", "lexiforest-curl-cffi-17dbd35d", "anacrolix-torrent-5561014e"}
cur = [l for l in open("cases/prep-out/prep.jsonl").read().splitlines() if l.strip()]
have = {re.search(r'"id": "([^"]+)"|PREP_FAIL ([^:]+):', l).group(1) or re.search(r'PREP_FAIL ([^:]+):', l).group(1) for l in cur}
out = list(cur)
for m in sorted(glob.glob("/srv/ci/secret/*/meta.json")):
    d = json.load(open(m))
    if d["id"] not in have: out.append(json.dumps({"id": d["id"], "prep": "ok", "test_cmd": d["test_cmd"], "hidden_cmd": d.get("hidden_cmd", ""), "rebuilt": True})); have.add(d["id"])
for w in sorted(glob.glob("cases/worker*.log")):
    for l in open(w):
        m = re.match(r"\[\d+\] prep failed: (.*)$", l.strip())
        if not m: continue
        t = m.group(1); i = re.search(r'"id": "([^"]+)"|PREP_FAIL ([^:]+):', t)
        cid = (i.group(1) or i.group(2)) if i else None
        if cid in RESET: continue                    # re-prepared after the tooling fixes: their old failure no longer holds
        if cid and cid not in have and not os.path.exists(f"/srv/ci/secret/{cid}/meta.json"): out.append(t); have.add(cid)
open("cases/prep-out/prep.jsonl.rebuilt", "w").write("".join(x + "\n" for x in out))
os.replace("cases/prep-out/prep.jsonl.rebuilt", "cases/prep-out/prep.jsonl")
print(len(out), "lines;", sum('"prep": "ok"' in x for x in out), "ok,", sum("fail" in x for x in out), "failed")
