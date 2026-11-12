#!/usr/bin/env python3
"""Focused review evidence; no VM, network, key file or official verdict writes.

Run: python3 verify.py. Uses Python stdlib, patch and Go.
These supplementary checks do not replace the frozen experiment's suites.
"""
import ast
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent
BLIND = HERE.parent
SPEC = importlib.util.spec_from_file_location("judge_server", BLIND.parents[1] / "judge/server.py")
JUDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JUDGE)
PACKETS = JUDGE.load_packets(BLIND / "packets")
BY_ID = {p["id"]: p for p in PACKETS}


def file_diff(diff, target):
    return next(s for s in re.split(r"(?=^diff --git )", diff, flags=re.M)
                if s.startswith(f"diff --git a/{target} b/{target}\n"))


def patched(root, target, source, diff):
    data = (HERE / "sources" / source).read_bytes()
    part = file_diff(diff, target)
    expected = re.search(r"^index ([0-9a-f]+)\.\.", part, re.M)[1]
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert actual.startswith(expected), (source, actual, expected)
    path = root / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    p = subprocess.run(["patch", "-p1", "--batch", "--forward"], input=part + "\n",
                       cwd=root, text=True, capture_output=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return path


def writer_checks(root):
    results = {}
    cases = [(p["id"], p["patch"]) for p in PACKETS if p["project"] == "gobwas/ws (Go)"]
    cases.append(("maintainer", BY_ID["0f490ef3"]["fix"]))
    for label, diff in cases:
        work = root / label
        target = patched(work, "wsflate/writer.go", "writer.go", diff)
        shutil.copyfile(HERE / "sources/cbuf.go", target.parent / "cbuf.go")
        shutil.copyfile(HERE / "writer_review_test.go", target.parent / "writer_review_test.go")
        env = dict(os.environ, GO111MODULE="off", GOCACHE=str(root / "go-cache"), GOTOOLCHAIN="local")
        p = subprocess.run(["go", "test", "-count=1", "-v", "."], cwd=target.parent,
                           env=env, text=True, capture_output=True)
        results[label] = {"exit_code": p.returncode, "output": p.stdout + p.stderr}
    assert results["maintainer"]["exit_code"] == 0, results["maintainer"]
    assert "decoded=\"first\"" in results["0f490ef3"]["output"], results["0f490ef3"]
    assert "Close accepted a compressor" in results["d987c7a4"]["output"], results["d987c7a4"]
    return results


def pyinfra_checks(root):
    results = {}
    cases = [(p["id"], p["patch"]) for p in PACKETS if p["project"] == "pyinfra-dev/pyinfra (Python)"]
    cases.append(("maintainer", BY_ID["4460dfce"]["fix"]))
    for label, diff in cases:
        source = patched(root / label, "src/pyinfra/api/facts.py", "facts.py", diff).read_text()
        tree = ast.parse(source)
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("get_fact", "_get_fact", "_make_command")]
        code = "from __future__ import annotations\n" + "\n".join(ast.unparse(n) for n in nodes)
        class TestFact:
            name = "review.fact"
            shell_executable = None
            command = "echo ok"
            requires_command = None
            def check_preconditions(self, *args, **kwargs): return None
            def default(self): return "default"
            def process(self, lines): return "ok"
        namespace = dict(
            ShortFactBase=type("ShortFactBase", (), {}), logger=MagicMock(),
            _handle_fact_kwargs=lambda *a: ({}, {"_su_user": "missing_user", "_ignore_errors": False}),
            CONNECTOR_ARGUMENT_KEYS={"_su_user", "_sudo_user"},
            get_kwargs_str=lambda k: str(k), StringCommand=lambda *a: a,
            QuoteString=lambda x: x, CommandOutput=lambda a: SimpleNamespace(stdout_lines=[], stderr_lines=[]),
            _SU_OUTPUT_MARKER="##PYINFRA_SU_READY##", _MISSING_COMMAND_MARKER="##PYINFRA_NOCMD##",
            SSHException=type("SSHException", (Exception,), {}),
            MissingCommandError=type("MissingCommandError", (Exception,), {}),
            FactPreconditionError=type("FactPreconditionError", (Exception,), {}),
            FactProcessError=type("FactProcessError", (Exception,), {}),
            SUDO_REGEX=r"^sudo: unknown user", SU_REGEXES=(r"^su: user .+ does not exist", r"^su: unknown login"),
            re=re, format_text=lambda s, **k: s, log_error_or_warning=MagicMock(),
            log_host_command_error=MagicMock(), print_host_combined_output=MagicMock(),
        )
        exec(compile(code, str(HERE / "sources/facts.py"), "exec"), namespace)
        state = MagicMock()
        host = MagicMock()
        host.connected = True
        host.run_shell_command.return_value = (False, SimpleNamespace(stdout_lines=[], stderr_lines=["su: user missing_user does not exist"]))
        try:
            result = namespace["get_fact"](state, host, TestFact)
            results[label] = {"result": result, "failed_hosts": state.fail_hosts.called}
        except Exception as error:
            results[label] = {"exception": type(error).__name__, "message": str(error)}
    for label in ("4460dfce", "bec0ff96"):
        assert results[label] == {"exception": "KeyError", "message": "'_sudo_user'"}, results[label]
    for label in ("5b9099b7", "aaed844e", "c10daf28", "e0265afe", "maintainer"):
        assert results[label] == {"result": "default", "failed_hosts": False}, results[label]
    return results


def static_checks():
    groups = collections.defaultdict(list)
    for p in PACKETS:
        groups[p["patch_hash"]].append(p["id"])
    # Confirm the exact omission responsible for Yarr's reported absence of hidden tests.
    prep = (BLIND.parents[1] / "cases/prep.py").read_text()
    match = re.search(r'^TESTFILE = re.compile\((.*)\)$', prep, re.M)
    matcher = re.compile(ast.literal_eval(match[1]))
    fixture = "src/parser/fixtures/atom/link-in-id.xml"
    assert not matcher.search(fixture)
    assert fixture in BY_ID["080bd524"]["fix"]
    # Count distinct byte-identical groups, without assuming one verdict per project.
    return {"packet_count": len(PACKETS), "hidden": dict(collections.Counter(p["hidden"] for p in PACKETS)),
            "identical_groups": [v for v in groups.values() if len(v) > 1],
            "yarr_fixture_classified_as_test": bool(matcher.search(fixture))}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="aip-blind-review-") as tmp:
        root = Path(tmp)
        result = {"scope": "supplementary local checks; not a rerun of the original experiment", 
                  "go": subprocess.check_output(["go", "version"], text=True).strip(),
                  "static": static_checks(), "writer": writer_checks(root / "writer"),
                  "pyinfra": pyinfra_checks(root / "pyinfra")}
        (HERE / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
