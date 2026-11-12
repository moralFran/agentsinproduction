#!/usr/bin/env python3
"""Runs ON aip-ci-01, after blind.py has added every round to the pool. Re-randomizes the whole pool so nothing outside
a packet's content tells which version it came from: every packet gets a new random id (file name and title), the key
is rewritten in a random order, and every packet file gets the same modification time. Then checks that no packet
mentions a run id, a round or a version label.   usage: blind-shuffle.py"""
import json, os, random, re, secrets
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
D = "results/blind/packets"
key = [json.loads(l) for l in open("results/blind/key.jsonl")]
by_old = {k["packet"]: k for k in key}
new_key, used = [], set()
staging = D + ".new"; os.makedirs(staging, exist_ok=True)
for old in random.sample(sorted(by_old), len(by_old)):
    while True:
        nid = secrets.token_hex(4)
        if nid not in used: used.add(nid); break
    text = open(f"{D}/{old}.md").read().replace(f"# Pacote {old}", f"# Pacote {nid}", 1)
    open(f"{staging}/{nid}.md", "w").write(text)
    new_key.append({"packet": nid, "run": by_old[old]["run"], "round": by_old[old]["round"]})
for f in os.listdir(D): os.remove(f"{D}/{f}")
for f in os.listdir(staging): os.replace(f"{staging}/{f}", f"{D}/{f}")
os.rmdir(staging)
random.shuffle(new_key)
open("results/blind/key.jsonl", "w").write("".join(json.dumps(k) + "\n" for k in new_key))
t = 1794441600                                      # 2026-11-12T00:00:00Z for every packet
for f in os.listdir(D): os.utime(f"{D}/{f}", (t, t))
leaks = [f for f in os.listdir(D) if re.search(r"\b(v1|v2|smoke)-[0-9a-f]{8}-r\d\b|\bround\b|\bv[12]\b|vers[aã]o", open(f"{D}/{f}").read(), re.I)]
print(f"{len(new_key)} packets re-randomized; same mtime on all; files mentioning a run id, round or version: {len(leaks)} {leaks[:5]}")
