#!/usr/bin/env python3
"""Offline regressions for fresh-run setup and audit resumption, added after collection.
Run from the public archive: python3 infra/test_workflow.py. Writes only to temporary directories; does not run case
code, contact a provider, or start pods. The pod invocation is the mocked boundary in the audit tests.
"""
import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_audit", ROOT / "cases/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FreshRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ci-workflow-")
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "fresh"

    def start(self, *args):
        subprocess.run(["bash", str(ROOT / "infra/new-run.sh"), str(self.dest), *args],
                       check=True, capture_output=True, text=True)

    def python(self, script):
        return subprocess.run([sys.executable, script], cwd=self.dest, check=True, capture_output=True, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_candidates_include_funnel_inputs(self):
        self.start("--with-candidates")
        for lang in ("go", "python"):
            for suffix in ("jsonl", "log"):
                path = f"mining/candidates-{lang}.{suffix}"
                self.assertEqual((self.dest / path).read_bytes(), (ROOT / path).read_bytes())
        self.assertEqual((self.dest / "cases/archived-cases.csv.sha256").read_bytes(),
                         (ROOT / "cases/cases.csv.sha256").read_bytes())
        # Before preparation, the funnel should report pending candidates, not fail for missing mining logs.
        (self.dest / "cases/prep-out").mkdir()
        (self.dest / "cases/prep-out/prep.jsonl").write_text("")
        (self.dest / "cases/repro.jsonl").write_text("")
        self.python("cases/recheck.py")
        self.python("cases/funnel.py")
        self.assertIn("Repositórios examinados: **1486**",
                      (self.dest / "cases/funnel.md").read_text())

    def test_both_modes_start_without_historical_judgments(self):
        for args in ((), ("--with-candidates",)):
            with self.subTest(args=args):
                self.dest = Path(self.tmp.name) / ("candidates" if args else "empty")
                self.start(*args)
                self.assertEqual(json.loads((self.dest / "results/blind/excluded.json").read_text()), {})
                for path in ("ARCHIVE", "cases/cases.csv", "results/attempts-v1.jsonl", "results/blind/verdicts.jsonl"):
                    self.assertFalse((self.dest / path).exists(), path)
                self.assertEqual((self.dest / "mining/candidates-go.jsonl").exists(), bool(args))

    def test_tally_works_with_new_exclusions_file(self):
        self.start()
        (self.dest / "cases/cases.csv").write_text("case_id,repo\nfixture,example/fixture\n")
        keys, verdicts = [], []
        for version in ("v1", "v2"):
            run, packet = f"{version}-fixture-r1", f"packet-{version}"
            attempt = {"run": run, "round": version, "case": "fixture", "rep": 1,
                       "agent": {"outcome": "finished"}, "executor": {"outcome": "green_no_hidden_tests"},
                       "gateway": {"spent_usd": 0.01}}
            (self.dest / f"results/attempts-{version}.jsonl").write_text(json.dumps(attempt) + "\n")
            keys.append(json.dumps({"run": run, "packet": packet}))
            verdicts.append({"packet": packet, "verdict": "equivalente", "source": "human"})
        (self.dest / "results/blind/key.jsonl").write_text("\n".join(keys) + "\n")
        with (self.dest / "results/blind/verdicts.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["packet", "verdict", "source"])
            writer.writeheader(); writer.writerows(verdicts)
        self.python("results/analyze.py")
        final = json.loads((self.dest / "results/final.json").read_text())
        self.assertEqual(final["main_cases"], ["example/fixture"])
        self.assertEqual(final["table"], {"v1": {"equivalente": 1}, "v2": {"equivalente": 1}})
        # A later exclusion is an explicit decision of the new run and is honored by the tally.
        (self.dest / "results/blind/excluded.json").write_text(json.dumps({"example/fixture": "synthetic reason"}))
        self.python("results/analyze.py")
        final = json.loads((self.dest / "results/final.json").read_text())
        self.assertEqual(final["main_cases"], [])
        self.assertIn("example/fixture", final["side"])

    def test_existing_destination_is_not_overwritten(self):
        self.start()
        path = self.dest / "results/blind/excluded.json"
        path.write_text('{"keep": "this decision"}\n')
        result = subprocess.run(["bash", str(ROOT / "infra/new-run.sh"), str(self.dest)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), '{"keep": "this decision"}\n')

    def test_tally_uses_actual_round_sizes_and_separates_tree_mutation(self):
        self.start()
        (self.dest/'cases/cases.csv').write_text('case_id,repo\nfixture,example/fixture\n')
        (self.dest/'results/blind/key.jsonl').write_text('')
        (self.dest/'results/blind/verdicts.csv').write_text('packet,verdict,source\n')
        for counts in ((2,2),(2,3)):
            with self.subTest(counts=counts):
                for version,count in zip(('v1','v2'),counts):
                    rows=[{'run':f'{version}-r{i}','round':version,'case':'fixture','rep':i,
                           'agent':{'outcome':'finished'},'executor':{'outcome':'test_changed_tree' if i==1 else 'rejected_by_validator'},
                           'gateway':{'spent_usd':0.01}} for i in range(1,count+1)]
                    (self.dest/f'results/attempts-{version}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                self.python('results/analyze.py')
                summary=(self.dest/'results/final-summary.md').read_text()
                self.assertNotIn('33 tentativas',summary)
                self.assertIn('todas as 2 tentativas por versão' if counts==(2,2) else 'todas as tentativas: v1 2, v2 3',summary)
                data=json.loads((self.dest/'results/final.json').read_text())
                self.assertEqual(data['table']['v1'],{'suíte alterou a árvore':1,'rejeitado pelo validador':1})


def completed_log(rc=0, apply_rc=0):
    return f"NOTES patch applied rc={apply_rc}\nCOMMAND TEST\nOUTPUT_BEGIN\nfixture result\nOUTPUT_END rc={rc} s=0.1\n"


class AuditResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ci-audit-resume-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "results"
        self.out.mkdir()
        self.cached = self.out / "fixture.log"

    def resume(self, cached, args=("all",)):
        self.cached.write_text(cached)
        pod_logs = self.root / "pods"
        pod_logs.mkdir(exist_ok=True)
        # A new pod result becomes visible only when the caller actually invokes the pod runner.
        def invoke(*a, **kw):
            (pod_logs / "au-fixture.log").write_text(completed_log())
            return subprocess.CompletedProcess(a[0], 0, "", "")
        with patch.object(audit, "POD_LOG_DIR", str(pod_logs)), patch.object(sys, "argv", ["audit.py", *args]), \
                patch.object(audit.subprocess, "run", side_effect=invoke) as pod, contextlib.redirect_stdout(io.StringIO()):
            result = audit.run(("fixture", "synthetic-case", None, False, str(self.out), "TEST"))
            return result, pod.call_count

    def test_failed_apply_is_retried(self):
        aborted = "NOTES patch applied rc=1\nCOMMAND TEST\nABORTED\nOUTPUT_END rc=apply_failed s=0.0\n"
        result, calls = self.resume(aborted)
        self.assertEqual(calls, 1)
        self.assertEqual(result, completed_log())
        self.assertEqual(self.cached.read_text(), completed_log())

    def test_truncated_or_invalid_logs_are_retried(self):
        for log in ("NO LOG", "NOTES \nCOMMAND TEST\nOUTPUT_BEGIN\npartial output\n",
                    "OUTPUT_END rc=0 s=0.1\n", completed_log() + "ABORTED\n", completed_log(apply_rc=1)):
            with self.subTest(log=log):
                self.assertEqual(self.resume(log)[1], 1)

    def test_completed_passes_and_test_failures_are_reused(self):
        for rc in (0, 1, -9):
            with self.subTest(rc=rc):
                self.assertEqual(self.resume(completed_log(rc)), (completed_log(rc), 0))

    def test_force_and_ws_still_rerun_completed_commands(self):
        for args in (("all", "--force"), ("ws", "fixed")):
            with self.subTest(args=args):
                self.assertEqual(self.resume(completed_log(), args)[1], 1)


if __name__ == "__main__":
    unittest.main()
