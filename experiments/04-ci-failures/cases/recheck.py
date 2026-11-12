#!/usr/bin/env python3
"""Re-applies criterion 9 (the fix must change at least one non-test source file) to every mined candidate with the
corrected test-file pattern (snapshot and golden files count as tests). Prints the candidates it now excludes and writes
cases/excluded-recheck.txt (one case id per line) for claim.py and freeze.py.   usage: recheck.py"""
import json, os, re, sys
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
TESTFILE = re.compile(r"(^|/)(tests?|testdata|testing|__snapshots__|golden)(/|$)|_test\.go$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|\.snap$|\.golden$")
ENVFILE = re.compile(r"(^|/)(go\.mod|go\.sum|requirements[^/]*\.txt|poetry\.lock|uv\.lock|Pipfile(\.lock)?|setup\.cfg|pyproject\.toml|tox\.ini|noxfile\.py|\.github/.*|Makefile|\.golangci\.ya?ml|\.pre-commit-config\.yaml|Dockerfile|\.tool-versions|\.python-version)$")
cid = lambda c: re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
out = []
for f in ("mining/candidates-go.jsonl", "mining/candidates-python.jsonl"):
    for l in open(f):
        c = json.loads(l)
        src = [n for n in c["fix_files"] if not TESTFILE.search(n) and not ENVFILE.search(n) and not n.lower().endswith((".md", ".rst", ".txt"))]
        if not src: out.append(cid(c)); print(cid(c), c["fix_files"][:4])
open("cases/excluded-recheck.txt", "w").write("".join(x + "\n" for x in out))
print(len(out), "excluded by the corrected criterion 9")
