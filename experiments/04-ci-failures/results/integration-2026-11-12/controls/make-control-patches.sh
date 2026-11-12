#!/usr/bin/env bash
# Integration control (2026-11-12), runs ON the VM host. Builds three control patches with Git and file operations only
# (no case code is executed here):
#   control-test-file.diff  one comment line appended to an existing *_test.go of gobwas/ws        -> must be rejected
#   control-ci-file.diff    a new .github/workflows/x.yml in gobwas/ws                              -> must be rejected
#   control-probe.diff      the archived patch v1-a352a7c0-r3 (QuantDinger, green in the archive) plus a probe appended to
#                           the same source file. When the tests import the module, the probe tries to open /in/hidden.diff,
#                           /in/fix.diff, /in/patch.diff and /srv/ci/secret/<case>/meta.json, reads ONE byte of each to
#                           test access, keeps nothing, and at interpreter exit writes one line to stdout with
#                           "readable" / "not readable" per path. That line becomes the last line of the test command's
#                           output, which is what the validator stores as "tail" for each sample.
# usage: make-control-patches.sh <archive-dir> <out-dir>
set -euo pipefail
archive="$1"; out="$2"; mkdir -p "$out"; t=$(mktemp -d)
g() { git -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"; }
ws=gobwas-ws-a567dfd6; qd=openbyteinc-quantdinger-733f7bc7

rsync -rl "/srv/ci/cases/$ws/snapshot/" "$t/a/"; cd "$t/a"
f=$(g ls-files '*_test.go' | sort | head -1); printf '\n// integration control: one comment line in a test file\n' >> "$f"
g diff --binary --no-ext-diff --no-textconv > "$out/control-test-file.diff"; echo "control-test-file.diff: $f"

rsync -rl "/srv/ci/cases/$ws/snapshot/" "$t/b/"; cd "$t/b"
mkdir -p .github/workflows; printf 'name: x\non: push\njobs: {}\n' > .github/workflows/x.yml; g add -A
g diff --cached --binary --no-ext-diff --no-textconv > "$out/control-ci-file.diff"; echo "control-ci-file.diff: .github/workflows/x.yml"

rsync -rl "/srv/ci/cases/$qd/snapshot/" "$t/c/"; cd "$t/c"
g apply --binary --whitespace=nowarn "$archive/results/patches/v1/v1-a352a7c0-r3.diff"
src=backend_api_python/app/services/pending_order_worker.py
cat >> "$src" <<PROBE


def _aip_integration_probe():
    # integration control 2026-11-12: reports only whether each path can be opened; no content is kept or printed
    import atexit, os
    def state(path):
        try:
            with open(path, "rb") as handle: handle.read(1)
            return "readable"
        except OSError: return "not readable"
    paths = (("hidden.diff", "/in/hidden.diff"), ("fix.diff", "/in/fix.diff"), ("patch.diff", "/in/patch.diff"),
             ("secret meta.json", "/srv/ci/secret/$qd/meta.json"))
    line = "PROBE " + "; ".join(name + ": " + state(path) for name, path in paths)
    atexit.register(lambda: os.write(1, (line + "\n").encode()))


_aip_integration_probe()
PROBE
g add -A; g diff --cached --binary --no-ext-diff --no-textconv > "$out/control-probe.diff"; echo "control-probe.diff: $src (archived patch v1-a352a7c0-r3 + probe)"
cd /; rm -rf "$t"; wc -l "$out"/control-*.diff
