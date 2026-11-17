#!/usr/bin/env bash
# Runs ON aip-ci-01. Writes a NEGATIVE CONTROL patch for a case: it "fixes" nothing and skips the failing test file
# instead (Go: t.Skip in every Test function of the first failing package's test files; Python: a module-level skip in
# the failing test file). The executor must reject it before running anything.   usage: control-skip.sh <case-id> <out.diff>
set -euo pipefail
cid="${1:?case}"; out="${2:?out}"; C=/srv/ci/cases/$cid; t=$(mktemp -d)
rsync -a "$C/snapshot/" "$t/r/"; cd "$t/r"
python3 - "$C/meta.json" <<'PY'
import json, pathlib, re, sys
m = json.load(open(sys.argv[1])); wd = pathlib.Path(m.get("workdir", "."))
if m["language"] == "Go":
    files = sorted(p for p in (pathlib.Path(".") / wd).rglob("*_test.go") if "/vendor/" not in str(p))[:1]
    for f in files: f.write_text(re.sub(r"(func Test\w+\(t \*testing\.T\) \{)", r"\1\n\tt.Skip(\"skipped\")", f.read_text()))
else:
    f = pathlib.Path(".") / wd / m["test_cmd"].split()[-1]
    f.write_text("import pytest\npytest.skip('skipped', allow_module_level=True)\n" + f.read_text())
PY
git add -A && git diff --cached > "$out"; rm -rf "$t"; echo "control patch: $(grep -c '^+++ ' "$out") file(s) changed, all of them tests"
