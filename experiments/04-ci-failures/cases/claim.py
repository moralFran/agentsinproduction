#!/usr/bin/env python3
"""Prints the next unclaimed candidate (Go and Python interleaved, in mining order) and claims it with a lock file."""
import itertools, json, os
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
rd = lambda p: [json.loads(l) for l in open(p)] if os.path.exists(p) else []
go, py = rd("mining/candidates-go.jsonl"), rd("mining/candidates-python.jsonl")
import re
skip = set(open("cases/excluded-recheck.txt").read().split()) if os.path.exists("cases/excluded-recheck.txt") else set()
cid = lambda c: re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
for c in (x for pair in itertools.zip_longest(go, py) for x in pair if x):
    if cid(c) in skip: continue                      # excluded by the corrected criterion 9 (recheck.py)
    key = c["repo"].replace("/", "__") + "__" + c["broken_sha"][:8]
    try: os.close(os.open(f"cases/locks/{key}", os.O_CREAT | os.O_EXCL)); print(json.dumps(c)); break
    except FileExistsError: continue
