#!/usr/bin/env python3
"""Local tests of experiment 05's harness logic. No cluster, no app code: a synthetic task in a temporary directory.
Covers: the pod mount contract (who can see a diff), the E4 exclusion rules, the job layout per task shape, the
F2P/P2P classification (criteria E1) and the validator's verdict logic (criteria E2) with a fake pod runner.
usage: python3 -I infra/test_team.py"""
import importlib.util, json, os, pathlib, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="team-test-")); os.environ["TEAM_ROOT"] = str(TMP)
def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE / rel); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
pod = load("pod", "cases/pod.py"); host = load("team_host", "cases/team_host.py"); val = load("validate", "cases/validate.py"); prep = load("prep_team", "cases/prep_team.py")

TID = "T0"; COMMIT_TEST = "test/a_test.dart"
JOBS = [{"name": "flutter-commit", "kind": "flutter", "area": "flutter", "scope": "commit", "in_scope": True, "files": [COMMIT_TEST]},
        {"name": "jest-commit", "kind": "jest", "area": "functions", "scope": "commit", "in_scope": False, "files": ["tests/x.test.js"]},
        {"name": "flutter-area", "kind": "flutter", "area": "flutter", "scope": "area", "in_scope": True, "exclude": [COMMIT_TEST], "procs": 4}]


def setup():
    for d in ("cases/T0/snapshot/lib", "cases/T0/snapshot/test", "secret/T0", "repro/T0", "work", "out"): (TMP / d).mkdir(parents=True, exist_ok=True)
    snap = TMP / "cases/T0/snapshot"
    (snap / "lib/a.dart").write_text("int f() => 1;\n"); (snap / COMMIT_TEST).write_text("void main() {}\n"); (snap / "pubspec.yaml").write_text("name: x\n")
    g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=snap, check=True, capture_output=True)
    g("init", "-q"); g("add", "-A"); g("commit", "-qm", "snapshot")
    (TMP / "cases/T0/meta.json").write_text(json.dumps({"id": TID, "workdir": ".", "node_dir": "/srv/ci/deps/node/node-0123abcd"}))
    (TMP / "secret/T0/meta.json").write_text(json.dumps({"id": TID, "n": 0, "snapshot_commit": "c0ffee", "snapshot_tar_sha256": "00", "jobs": JOBS,
                                                         "tests_put_back": [COMMIT_TEST, "lib/internal/firebase/functions/tests/x.test.js"]}))


def write_sample(tree, job, rep, cases, file_errors=None, outcome="sampled"):
    r = {"executor": {"outcome": outcome, "tool": {"s": 10.0, "rc": 0}, "counts": {}}, "pod": {"wall_s": 40.0}, "limits": {"cpu": "2", "memory": "4Gi"},
         "result": None if outcome != "sampled" else {"cases": cases, "file_errors": file_errors or {}, "failure_text": "FAIL test/a_test.dart::a\nboom\n\nsecond paragraph of a\n\nFAIL test/other_test.dart::c\nold\n\nmore of c"}}
    (TMP / "repro/T0" / f"{tree}-{job}-{rep}.json").write_text(json.dumps(r))


class Contract(unittest.TestCase):
    def spec(self, role, tree=None, patch=None):
        meta = json.load(open(TMP / "cases/T0/meta.json"))
        return pod.build_spec(role, TID, "p", 600, ["python3", "-u", "/code/team.py", "run"], meta, patch, tree=tree, out_dir="/srv/ci/out/p" if role == "exec" else None)

    def test_test_container_sees_no_diff_and_no_secret(self):
        for tree, patch in (("baseline", None), ("gold", None), ("patch", "/x/p.diff")):
            s = self.spec("exec", tree, patch)["spec"]; c = s["containers"][0]; paths = [m["mountPath"] for m in c["volumeMounts"]]
            self.assertFalse([p for p in paths if p.startswith("/in")], tree)
            self.assertFalse([p for p in paths if "/secret" in p], tree)
            self.assertEqual([m["mountPath"] for m in c["volumeMounts"] if not m.get("readOnly")], ["/srv/ci/cases/T0/repo", "/tmp", "/out"])
            names = [i["name"] for i in s["initContainers"]]; self.assertEqual(names, ["prepare", "netgate"])
            init = [m["mountPath"] for m in s["initContainers"][0]["volumeMounts"]]
            self.assertEqual("/in/fix.diff" in init, tree == "gold"); self.assertEqual("/in/patch.diff" in init, tree == "patch")
            self.assertEqual(s["initContainers"][1]["volumeMounts"], [])
            secret_vols = [v for v in s["volumes"] if "/srv/ci/secret" in json.dumps(v)]
            self.assertEqual(len(secret_vols), 1 if tree == "gold" else 0)
            self.assertEqual(s["runtimeClassName"], "kata-qemu"); self.assertFalse(s["automountServiceAccountToken"])

    def test_agent_pod_has_no_diff_no_secret_no_result_dir(self):
        s = self.spec("agent")["spec"]; dump = json.dumps(s)
        self.assertNotIn("/srv/ci/secret", dump); self.assertNotIn("/in/", dump); self.assertNotIn("/srv/ci/out", dump)
        self.assertEqual(s["containers"][0]["volumeMounts"][0], {"name": "case", "mountPath": "/srv/ci/cases/T0", "readOnly": True})
        with self.assertRaises(ValueError): self.spec("agent", patch="/x/p.diff")
        with self.assertRaises(ValueError): self.spec("exec", tree="fixed")

    def test_dependency_mount_is_read_only_and_checked(self):
        s = self.spec("exec", "baseline")["spec"]
        m = [m for m in s["containers"][0]["volumeMounts"] if m["name"] == "nodedeps"][0]
        self.assertTrue(m["readOnly"]); self.assertEqual(m["mountPath"], "/srv/ci/deps/node/node-0123abcd")
        with self.assertRaises(ValueError): pod.deps_mounts(TID, {"node_dir": "/srv/ci/secret/T0"})


class Rules(unittest.TestCase):
    def test_e4_exclusions(self):
        gone = ["CLAUDE.md", "AGENTS.md", "docs/plans/x.md", "docs/tech-debt/y.md", "gcp/config.sh", "ops/a", "dev-env/b", "load-tests/c", ".github/workflows/x.yml",
                ".vscode/launch.json", ".firebase/hosting.cache", ".gitleaks.toml", ".gitleaksignore", "scripts/security/a.sh", "scripts/tests/t.py",
                "integration_test/tool/x.dart", "perf_report.html", "android/app/google-services.json", "android/app/src/staging/google-services.json",
                "ios/Runner/GoogleService-Info.plist", "lib/internal/firebase/.firebaserc", "lib/internal/firebase/.firebase/x", "sub/CLAUDE.md", ".superpowers/x"]
        kept = ["README.md", "Makefile", "pubspec.yaml", "lib/docs/x.dart", "scripts/hooks/pre-commit", "scripts/public_client_flutter_flags.sh", "integration_test/app_test.dart",
                "lib/internal/firebase/firebase.json", "lib/internal/firebase/firestore.rules", "test/a_test.dart", "vendor/cloud_firestore/pubspec.yaml", "web/privacy.html",
                "docs.md", "lib/gcp/x.dart", "android/app/build.gradle.kts", "ios/Runner/Info.plist"]
        self.assertEqual([p for p in gone if not prep.excluded(p)], []); self.assertEqual([p for p in kept if prep.excluded(p)], [])

    def test_job_layout(self):
        FB = "lib/internal/firebase"
        man = lambda src, tests: {"source": src, "tests": tests}
        names = lambda m: [(j["name"], j["in_scope"]) for j in prep.jobs_for({}, m)[0]]
        self.assertEqual(names(man([f"{FB}/firestore.rules"], [f"{FB}/functions/tests/rules.test.js"])), [("jest-commit", True), ("rules-area", True)])
        self.assertEqual(names(man(["lib/a.dart"], ["test/a_test.dart"])), [("flutter-commit", True), ("flutter-area", True)])
        t3 = names(man([f"{FB}/functions/index.js"], [f"{FB}/functions/tests/http.test.js", "test/p_test.dart"]))
        self.assertEqual(t3, [("flutter-commit", False), ("jest-commit", True), ("functions-area-1", True), ("functions-area-2", True), ("functions-area-3", True)])
        t7 = names(man(["lib/a.dart"], ["test/s_test.dart", f"{FB}/functions/tests/acc.test.js", f"{FB}/functions/tests/e2e-functions/j.e2e.test.js"]))
        self.assertEqual(t7, [("flutter-commit", True), ("jest-commit", False), ("e2e-functions-commit", False), ("flutter-area", True)])
        jobs = prep.jobs_for({}, man([f"{FB}/functions/index.js", f"{FB}/firestore.rules", "lib/a.dart"], [f"{FB}/functions/tests/rules.test.js", "test/a_test.dart"]))[0]
        area = [j for j in jobs if j["name"].startswith("functions-area")]
        self.assertEqual([j["shard"] for j in area], [[0, 3], [1, 3], [2, 3]]); self.assertEqual(area[0]["exclude"], ["tests/rules.test.js"])
        self.assertFalse([j for j in jobs if j["name"] == "rules-area"])        # covered by the functions suite, which holds the rules files


class Classify(unittest.TestCase):
    def test_lists(self):
        A = COMMIT_TEST
        for rep in (1, 2, 3):
            write_sample("baseline", "flutter-commit", rep, {f"{A}::old": "pass", f"{A}::broken": "fail", f"{A}::skipped": "skip", f"{A}::flaky": "pass" if rep < 3 else "fail", f"{A}::a": "fail"})
            write_sample("gold", "flutter-commit", rep, {f"{A}::old": "pass", f"{A}::broken": "fail", f"{A}::skipped": "skip", f"{A}::flaky": "pass", f"{A}::a": "pass", f"{A}::b": "pass"})
            write_sample("baseline", "jest-commit", rep, {}, {"lib/internal/firebase/functions/tests/x.test.js": "test file failed to run"})
            write_sample("gold", "jest-commit", rep, {"lib/internal/firebase/functions/tests/x.test.js::n": "pass", "lib/internal/firebase/functions/tests/x.test.js::sk": "skip"})
            write_sample("baseline", "flutter-area", rep, {"test/o_test.dart::p": "pass", "test/o_test.dart::c": "fail", "test/o_test.dart::regress": "pass", "test/o_test.dart::helped": "fail"})
            write_sample("gold", "flutter-area", rep, {"test/o_test.dart::p": "pass", "test/o_test.dart::c": "fail", "test/o_test.dart::regress": "fail", "test/o_test.dart::helped": "pass"})
        out, failure = host.classify(TID)
        got = lambda k: sorted(e["case"].split("::")[-1] for e in out[k])
        self.assertEqual(got("f2p"), ["a", "n"])                           # n: its whole file failed to run on baseline
        self.assertEqual(got("p2p"), ["old", "p"])
        self.assertEqual(got("excluded_fail_both"), ["broken", "c"]); self.assertEqual(got("unstable"), ["b", "flaky"])   # b: absent on baseline though its file ran
        self.assertEqual(got("skipped"), ["sk", "skipped"]); self.assertEqual(got("broken_by_gold"), ["regress"]); self.assertEqual(got("fixed_outside_commit_tests"), ["helped"])
        self.assertTrue(out["usable"]); self.assertIn("FAIL test/a_test.dart::a", failure); self.assertNotIn("other_test", failure)
        self.assertIn("second paragraph of a", failure); self.assertNotIn("more of c", failure)

    def test_performance_case_is_in_no_list(self):
        perf = next(iter(host.PERFORMANCE_CASES))
        for rep in (1, 2, 3):
            for tree in ("baseline", "gold"):
                write_sample(tree, "flutter-area", rep, {"test/o_test.dart::p": "pass", **({perf: "pass"} if rep == 1 else {})})   # old samples hold it, new ones do not
        out, _ = host.classify(TID)
        listed = [e["case"] for k in ("f2p", "p2p", "unstable", "excluded_fail_both", "skipped", "broken_by_gold") for e in out[k]]
        self.assertNotIn(perf, listed); self.assertEqual([e["case"] for e in out["not_run_performance"]], [perf])
        self.assertIn("test/o_test.dart::p", [e["case"] for e in out["p2p"]])
        team = load("team", "executor/team.py"); import re
        rx = re.compile(team.name_filter(team.NEVER_RUN_FLUTTER))
        self.assertIsNone(rx.search(perf.split("::", 1)[1]))
        for other in ("Timing group another case - documented pattern", "x Timing group timing case (name redacted)",
                      "Timing group timing case (name redacted) 2", "a (b) [c] d"):
            self.assertIsNotNone(rx.search(other), other)
        self.assertEqual(team.name_filter(["a.b (c)"]), "^(?!(?:a\\.b \\(c\\))$)")

    def test_out_of_scope_commit_tests_and_missing_samples(self):
        for rep in (1, 2, 3):
            for tree in ("baseline", "gold"): write_sample(tree, "jest-commit", rep, {"lib/internal/firebase/functions/tests/x.test.js::same": "pass"})
        out, _ = host.classify(TID)
        self.assertEqual([e["case"].split("::")[-1] for e in out["commit_tests_pass_both_out_of_scope"]], ["same"])
        write_sample("gold", "flutter-area", 2, {}, outcome="infra_error")
        out, _ = host.classify(TID)
        self.assertFalse(out["usable"]); self.assertTrue(any("gold-flutter-area-2" in p for p in out["problems"]))
        self.assertFalse([e for e in out["p2p"] if e["job"] == "flutter-area"])  # an incomplete job contributes no list


class Verdict(unittest.TestCase):
    """criteria E10: stage 1 = commit jobs x3; stage 2 = one sample of each area job + two reruns of the failing files."""
    F2P, OLD, P2P, Q2P = f"{COMMIT_TEST}::a", f"{COMMIT_TEST}::old", "test/o_test.dart::p", "test/q_test.dart::q"
    def setUp(self):
        (TMP / "secret/T0/cases.json").write_text(json.dumps({"f2p": [{"job": "flutter-commit", "case": self.F2P}],
            "p2p": [{"job": "flutter-commit", "case": self.OLD}, {"job": "flutter-area", "case": self.P2P}, {"job": "flutter-area", "case": self.Q2P}]}))
        self.calls = []; self.patch = str(TMP / "p.diff")
        pathlib.Path(self.patch).write_text("diff --git a/lib/a.dart b/lib/a.dart\n--- a/lib/a.dart\n+++ b/lib/a.dart\n@@ -1 +1 @@\n-int f() => 1;\n+int f() => 2;\n")

    def runner(self, bad=None, outcome=None, file_error=None, dirty=None):
        """bad: {(job name, sample label): {case: status or None (absent)}}; outcome: {(job, label): non-result outcome};
        file_error: {(job, label): [files that did not load]} (their cases are absent from the result);
        dirty: {(job, label): {file: per-file status}} (E22: the file ended in error, its cases stay as reported)."""
        def run(tid, tree, job, name, patch=None):
            label = name.rsplit("-", 1)[-1]; key = (job["name"], label); self.calls.append((job["name"], label, tuple(job.get("files") or ())))
            if (outcome or {}).get(key): return {"executor": {"outcome": outcome[key], "why": "x"}, "pod": {}, "result": None}
            if job["name"] == "flutter-commit": cases = {self.F2P: "pass", self.OLD: "pass"}
            else: cases = {c: "pass" for c in (self.P2P, self.Q2P) if not job.get("files") or c.split("::")[0] in job["files"]}
            for case, status in ((bad or {}).get(key) or {}).items():
                if status is None: cases.pop(case, None)
                else: cases[case] = status
            ferr = {f: "loading: error" for f in (file_error or {}).get(key, [])}
            cases = {c: s for c, s in cases.items() if c.split("::")[0] not in ferr}
            return {"executor": {"outcome": "sampled", "tool": {"s": 1}, "counts": {}}, "pod": {"wall_s": 2}, "limits": {"cpu": "2", "memory": "4Gi"},
                    "result": {"cases": cases, "file_errors": ferr, "file_times": dict((dirty or {}).get(key) or {}), "files": ["lib/a.dart"]}}
        return run
    V = lambda self, **kw: val.validate_task(TID, self.patch, runner=self.runner(**{k: v for k, v in kw.items() if k != "run_all"}), run_all=kw.get("run_all", False))

    def test_clean_patch_is_resolved_in_stage_2_with_four_pods(self):
        v = self.V()
        self.assertEqual((v["outcome"], v["decided_in_stage"], len(v["samples"])), ("resolved", 2, 4))
        self.assertEqual([c[:2] for c in self.calls], [("flutter-commit", "1"), ("flutter-commit", "2"), ("flutter-commit", "3"), ("flutter-area", "s2")])
        self.assertEqual((v["broken"], v["unstable_in_attempt"], v["stage2"]["rerun_samples"]), ([], [], 0))

    def test_stage_1_failure_skips_stage_2(self):
        for bad in ({("flutter-commit", "2"): {self.F2P: "fail"}}, {("flutter-commit", "1"): {self.F2P: None}}, {("flutter-commit", "3"): {self.OLD: "fail"}},
                    {("flutter-commit", "3"): {self.OLD: "skip"}}):
            self.calls = []; v = self.V(bad=bad)
            self.assertEqual((v["outcome"], v["decided_in_stage"], len(v["samples"]), v["stage2"]), ("not_resolved", 1, 3, None), bad)
            self.assertFalse([c for c in self.calls if c[0] != "flutter-commit"])
        v = self.V(file_error={("flutter-commit", "1"): [COMMIT_TEST]})                 # the commit's test file does not load in one sample
        self.assertEqual((v["outcome"], v["decided_in_stage"], v["stage1"]["f2p_failed"], v["stage1"]["p2p_failed"]), ("not_resolved", 1, 1, 1))
        v = self.V(bad={("flutter-commit", "2"): {self.F2P: "fail"}}, run_all=True)      # --all: stage 2 runs, the verdict does not change
        self.assertEqual((v["outcome"], v["decided_in_stage"], len(v["samples"])), ("not_resolved", 1, 4))

    def test_E22_required_case_in_a_file_that_ended_in_error_is_not_passed(self):
        # stage 1: every case says pass, the commit's test file timed out after them (or is red without a failed case)
        for st in ({"rc": 124}, {"rc": 1, "file_status": "failed_without_failed_case"}):
            v = self.V(dirty={("flutter-commit", "2"): {COMMIT_TEST: st}})
            self.assertEqual((v["outcome"], v["decided_in_stage"], v["stage1"]["f2p_failed"], v["stage1"]["p2p_failed"]), ("not_resolved", 1, 1, 1), st)
            self.assertEqual([s["dirty_files"] for s in v["samples"]], [0, 1, 0])
            self.assertIn(COMMIT_TEST, v["samples"][1]["dirty_files_with_required_cases"])
        # a clean file whose process merely exited non-zero for another reason is not dirty (rc alone decides nothing)
        self.assertEqual(self.V(dirty={("flutter-commit", "2"): {COMMIT_TEST: {"rc": 1}}})["outcome"], "resolved")
        # a dirty file that holds no required case changes nothing
        self.assertEqual(self.V(dirty={("flutter-area", "s2"): {"test/other_test.dart": {"rc": 124}}})["outcome"], "resolved")
        # stage 2: the area file is dirty with the patch every time and clean with the owner's fix => broken
        O = "test/o_test.dart"; red = {O: {"rc": 1, "file_status": "failed_without_failed_case"}}
        v = self.V(dirty={("flutter-area", "s2"): red, **{("flutter-area-rr", k): red for k in ("1", "2", "3")}})
        self.assertEqual((v["outcome"], [b["case"] for b in v["broken"]]), ("not_resolved", [self.P2P]))
        # dirty with the owner's fix at the same time too => environment_dependent, does not count against the patch
        v = self.V(dirty={("flutter-area", "s2"): red, **{("flutter-area-rr", k): red for k in ("1", "2")}, ("flutter-area-ck", "g1"): red})
        self.assertEqual((v["outcome"], [e["case"] for e in v["environment_dependent"]], v["broken"]), ("resolved", [self.P2P], []))
        # dirty once, clean in both reruns => unstable in the attempt, reported, not counted
        v = self.V(dirty={("flutter-area", "s2"): red})
        self.assertEqual((v["outcome"], [u["case"] for u in v["unstable_in_attempt"]]), ("resolved", [self.P2P]))

    def test_E23_file_killed_before_any_case_is_a_timeout_not_a_verdict(self):
        v = self.V(file_error={("flutter-commit", "2"): [COMMIT_TEST]}, dirty={("flutter-commit", "2"): {COMMIT_TEST: {"rc": 124, "s": 300.4}}})
        self.assertEqual((v["outcome"], v["decided_in_stage"]), ("timeout", 1)); self.assertIn("E23", v["why"])
        # the same file not loading for another reason (no rc 124) is still a failure about the patch
        self.assertEqual(self.V(file_error={("flutter-commit", "2"): [COMMIT_TEST]})["outcome"], "not_resolved")
        # killed AFTER reporting cases (cases of the file present): not E23; the file is dirty (E22) => not_resolved
        self.assertEqual(self.V(dirty={("flutter-commit", "2"): {COMMIT_TEST: {"rc": 124}}})["outcome"], "not_resolved")
        # in stage 2 too: the validation ends as timeout, never resolved
        v = self.V(file_error={("flutter-area", "s2"): ["test/o_test.dart"]}, dirty={("flutter-area", "s2"): {"test/o_test.dart": {"rc": 124}}})
        self.assertEqual((v["outcome"], v["decided_in_stage"]), ("timeout", 2))

    def test_E22_dirty_files_reads_the_executor_result(self):
        res = {"file_errors": {"a": "timeout", "b": "loading x: error"}, "files": ["lib/patched.dart"],
               "file_times": {"a": {"rc": 124}, "c": {"rc": 124}, "d": {"rc": 1, "file_status": "failed_without_failed_case"}, "e": {"rc": 0}, "f": {"rc": 1}, "g": {}}}
        self.assertEqual(val.dirty_files(res), {"a": "timeout", "b": "loading x: error", "c": "timeout", "d": "file red without a failed case"})
        for broken in ({}, {"file_errors": {}}, {"file_errors": {}, "file_times": ["x"]}, {"file_errors": None, "file_times": {}}):
            with self.assertRaises(ValueError): val.dirty_files(broken)
        # a sample whose result cannot be read this way is not a result: the validation ends as infra_error, never resolved
        def run(tid, tree, job, name, patch=None):
            return {"executor": {"outcome": "sampled", "tool": {"s": 1}}, "pod": {}, "result": {"cases": {self.F2P: "pass", self.OLD: "pass"}, "file_errors": {}, "files": {}}}
        v = val.validate_task(TID, self.patch, runner=run)
        self.assertEqual((v["outcome"], v["decided_in_stage"]), ("infra_error", 1)); self.assertIn("unreadable sample result", v["why"])

    def test_E22_contract_with_the_real_executor_record(self):
        """The record executor/team.py writes, built by its own Jest collector from Jest's own output format, read by the
        validator: a timeout after the assertions and a red file without a failed case are both dirty."""
        import re
        src = (HERE / "executor" / "team.py").read_text()
        m = re.search(r'detail = \{\*\*r, "tool": tool, "cases": out\.cases, "file_errors": out\.file_errors, "file_times": out\.files,', src)
        self.assertTrue(m, "executor/team.py no longer writes cases/file_errors/file_times this way: update validate.dirty_files and this test")
        self.assertRegex(src, r'"files": prepared\.get\("files", \[\]\)')                      # `files` = what the patch touches (a list)
        team = load("executor_team_contract", "executor/team.py"); scratch = TMP / "contract"; jd = scratch / "job/jest"; jd.mkdir(parents=True, exist_ok=True)
        team.REPO, team.JOBDIR = str(scratch / "repo"), str(scratch / "job"); fdir = team.REPO + "/lib/internal/firebase/functions"
        names = ["tests/timeout.test.js", "tests/afterall.test.js", "tests/clean.test.js"]
        (jd / "status.json").write_text(json.dumps({names[0]: {"i": 0, "rc": 124, "s": 300}, names[1]: {"i": 1, "rc": 1, "s": 3}, names[2]: {"i": 2, "rc": 0, "s": 2}}))
        for i, status in enumerate(("passed", "failed", "passed")):
            (jd / f"{i}.json").write_text(json.dumps({"testResults": [{"status": status, "message": "", "assertionResults": [{"fullName": "required", "status": "passed"}]}]}))
        out = team.Cases(); team.collect_jest({}, out, fdir, names)
        detail = {"outcome": "sampled", "files": ["lib/a.js"], "tool": {"rc": 124}, "cases": out.cases, "file_errors": out.file_errors, "file_times": out.files}
        self.assertEqual(set(out.cases.values()), {"pass"})                                     # every case says pass
        pre = "lib/internal/firebase/functions/"
        self.assertEqual(val.dirty_files(detail), {pre + names[0]: "timeout", pre + names[1]: "file red without a failed case"})
        # the whole path: those cases required, that record as the sample => not resolved
        (TMP / "secret/T0/cases.json").write_text(json.dumps({"f2p": [{"job": "flutter-commit", "case": f"{pre}{n}::required"} for n in names], "p2p": []}))
        for bad, want in ((names[0], "not_resolved"), (names[1], "not_resolved"), (None, "resolved")):
            d = dict(detail, file_errors={k: w for k, w in out.file_errors.items() if bad and k.endswith(bad)},
                     file_times={k: (st if bad and k.endswith(bad) else {"rc": 0, "s": 1}) for k, st in out.files.items()})
            v = val.validate_task(TID, self.patch, runner=lambda *a, **k: {"executor": {"outcome": "sampled", "tool": {"s": 1}}, "pod": {}, "result": d})
            self.assertEqual(v["outcome"], want, bad)

    def test_E22_keep_result_keeps_every_sample_and_overwrites_nothing(self):
        import gzip
        keep = TMP / "keep"; os.environ["KEEP_RESULTS"] = str(keep)
        try:
            for n in (1, 2): host.keep_result("va-x-s2", {"cases": {"f::c": "pass"}, "n": n}, {"outcome": "sampled"}, {"phase": "Succeeded/"})
            names = sorted(f.name for f in keep.iterdir()); self.assertEqual(names, ["va-x-s2.2.json.gz", "va-x-s2.json.gz"])
            self.assertEqual([json.load(gzip.open(keep / f))["result"]["n"] for f in names], [2, 1])
            os.environ["KEEP_RESULTS"] = ""; self.assertIsNone(host.keep_result("va-y", {}, {}, {})); self.assertEqual(len(list(keep.iterdir())), 2)
            # a place that cannot be written: the failure is raised, nothing half-written is left
            blocked = TMP / "blocked"; blocked.write_text("a file where the directory should be"); os.environ["KEEP_RESULTS"] = str(blocked)
            with self.assertRaises(OSError): host.keep_result("va-z", {"cases": {}}, {}, {})
            os.environ["KEEP_RESULTS"] = str(keep); real = host.os.replace
            def full(*a): raise OSError(28, "No space left on device")
            host.os.replace = full
            try:
                with self.assertRaises(OSError): host.keep_result("va-w", {"cases": {}}, {}, {})
            finally: host.os.replace = real
            self.assertEqual(sorted(f.name for f in keep.iterdir()), names)                    # no file, no .tmp left behind
        finally: os.environ.pop("KEEP_RESULTS", None)

    def test_E22_a_sample_whose_result_cannot_be_kept_is_not_a_result_and_the_original_stays(self):
        out_dir = TMP / "out" / "vx-t0-p-flutter-commit-1"; real_run, real_keep, real_build = host.pod.run_pod, host.keep_result, host.pod.build_spec
        def run_pod(spec, patch):
            out_dir.mkdir(parents=True, exist_ok=True); (out_dir / "result.json").write_text(json.dumps({"cases": {self.F2P: "pass"}, "file_errors": {}, "file_times": {}}))
            return 'EXECUTOR {"outcome": "sampled"}\n', {"phase": "Succeeded/"}
        def disk_full(*a): raise OSError("could not keep the result of x: [Errno 28] No space left on device")
        host.pod.run_pod, host.keep_result, host.pod.build_spec = run_pod, disk_full, lambda *a, **k: {}
        try: r = host._sample(TID, "patch", JOBS[0], out_dir.name, self.patch, "2", "4Gi")
        finally: host.pod.run_pod, host.keep_result, host.pod.build_spec = real_run, real_keep, real_build
        self.assertEqual((r["executor"]["outcome"], r["result"]), ("infra_error", None)); self.assertIn("No space left", r["executor"]["why"])
        self.assertTrue((out_dir / "result.json").exists())                                    # the original was not deleted

    def test_fail_then_fail_is_broken(self):
        # E18: broken = fails first, in at least one rerun, passes with the owner's fix at the same time, fails again after it
        for reruns in ({("flutter-area-rr", "1"): {self.P2P: "fail"}, ("flutter-area-rr", "2"): {self.P2P: "fail"}},
                       {("flutter-area-rr", "2"): {self.P2P: "fail"}},                    # fail, pass, fail: one failing rerun is enough
                       {("flutter-area-rr", "1"): {self.P2P: None}}):                       # absent in a rerun = not passed
            self.calls = []; v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail"}, ("flutter-area-rr", "3"): {self.P2P: "fail"}, **reruns})
            self.assertEqual((v["outcome"], v["decided_in_stage"]), ("not_resolved", 2), reruns)
            self.assertEqual([b["case"] for b in v["broken"]], [self.P2P]); self.assertEqual((v["unstable_in_attempt"], v["environment_dependent"]), ([], []))
            rr = [c for c in self.calls if c[0] == "flutter-area-rr"]
            self.assertEqual([(c[1], c[2]) for c in rr], [(n, ("test/o_test.dart",)) for n in "123"])                   # that file only
            self.assertEqual([c for c in self.calls if c[0] == "flutter-area-ck"], [("flutter-area-ck", "g1", ("test/o_test.dart",))])
            self.assertEqual([s["tree"] for s in v["samples"]][-2:], ["gold", "patch"])                              # the control, then sample 3

    def test_case_that_fails_with_the_owner_fix_too_is_environment_dependent(self):
        """The clock case of 16/11: fails with any patch between 03:00 and 04:00 UTC, and with the owner's fix as well."""
        self.calls = []
        v = self.V(bad={(j, l): {self.P2P: "fail"} for j, l in (("flutter-area", "s2"), ("flutter-area-rr", "1"), ("flutter-area-rr", "2"), ("flutter-area-ck", "g1"))})
        self.assertEqual((v["outcome"], v["decided_in_stage"], v["broken"], v["unstable_in_attempt"]), ("resolved", 2, [], []))
        self.assertEqual([e["case"] for e in v["environment_dependent"]], [self.P2P]); self.assertEqual(v["stage2"]["environment_dependent"], 1)
        self.assertFalse([c for c in self.calls if c[:2] == ("flutter-area-rr", "3")])                                  # nothing left to confirm
        # two cases failed again: one fails on the owner's tree too, the other passes there and fails again with the patch
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail", self.Q2P: "fail"}, ("flutter-area-rr", "1"): {self.P2P: "fail", self.Q2P: "fail"},
                        ("flutter-area-ck", "g1"): {self.P2P: "fail"}, ("flutter-area-rr", "3"): {self.Q2P: "fail"}})
        self.assertEqual((v["outcome"], [b["case"] for b in v["broken"]], [e["case"] for e in v["environment_dependent"]]), ("not_resolved", [self.Q2P], [self.P2P]))

    def test_passes_with_owner_fix_and_again_with_the_patch_is_unstable(self):
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail"}, ("flutter-area-rr", "1"): {self.P2P: "fail"}, ("flutter-area-rr", "2"): {self.P2P: "fail"}})
        self.assertEqual((v["outcome"], v["broken"], v["environment_dependent"]), ("resolved", [], []))
        self.assertEqual([(u["case"], u["failed_after_control"]) for u in v["unstable_in_attempt"]], [(self.P2P, False)])

    def test_control_sample_that_is_not_a_result_is_not_a_verdict(self):
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail"}, ("flutter-area-rr", "1"): {self.P2P: "fail"}}, outcome={("flutter-area-ck", "g1"): "pod_failed"})
        self.assertEqual((v["outcome"], v["decided_in_stage"]), ("infra_error", 2))

    def test_fail_then_pass_pass_is_unstable_and_resolved(self):
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail", self.Q2P: "fail"}, ("flutter-area-rr", "1"): {self.Q2P: "fail"}, ("flutter-area-rr", "3"): {self.Q2P: "fail"}})
        self.assertEqual((v["outcome"], v["decided_in_stage"]), ("not_resolved", 2))
        self.assertEqual(([b["case"] for b in v["broken"]], [u["case"] for u in v["unstable_in_attempt"]]), ([self.Q2P], [self.P2P]))
        self.assertEqual(v["stage2"]["files_rerun"], {"flutter-area": ["test/o_test.dart", "test/q_test.dart"]})
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail"}})
        self.assertEqual((v["outcome"], v["decided_in_stage"], v["broken"]), ("resolved", 2, []))
        self.assertEqual([u["case"] for u in v["unstable_in_attempt"]], [self.P2P]); self.assertEqual(len(v["samples"]), 6)

    def test_file_load_error_counts_as_its_cases_failing(self):
        v = self.V(file_error={("flutter-area", "s2"): ["test/o_test.dart"]})              # loads again in both reruns
        self.assertEqual((v["outcome"], [u["case"] for u in v["unstable_in_attempt"]]), ("resolved", [self.P2P]))
        v = self.V(file_error={("flutter-area", "s2"): ["test/o_test.dart"], ("flutter-area-rr", "2"): ["test/o_test.dart"], ("flutter-area-rr", "3"): ["test/o_test.dart"]})
        self.assertEqual((v["outcome"], v["decided_in_stage"], [b["case"] for b in v["broken"]]), ("not_resolved", 2, [self.P2P]))

    def test_jest_rerun_job_keeps_project_and_environment(self):
        job = {"name": "functions-area-2", "kind": "jest", "area": "functions", "scope": "area", "project": "app-test", "globs": ["tests/*.test.js"],
               "exclude": ["tests/a.test.js"], "shard": [1, 3], "env": {"FIREBASE_RULES_TEST_PROJECT_ID": "app-test"}}
        r = val.rerun_job(job, ["lib/internal/firebase/functions/tests/e2e/b.test.js", "lib/internal/firebase/functions/tests/c.test.js"])
        self.assertEqual(r["files"], ["tests/c.test.js", "tests/e2e/b.test.js"]); self.assertEqual((r["project"], r["env"], r["kind"]), ("app-test", job["env"], "jest"))
        self.assertFalse({"globs", "shard", "exclude"} & set(r)); self.assertEqual(r["name"], "functions-area-2-rr")

    def test_infrastructure_and_integrity_are_not_verdicts(self):
        for where in (("flutter-commit", "2"), ("flutter-area", "s2")):
            for outcome, want in (("infra_error", "infra_error"), ("test_changed_tree", "test_changed_tree"), ("timeout", "timeout"), ("weird", "infra_error")):
                v = self.V(outcome={where: outcome}); self.assertEqual((v["outcome"], v["decided_in_stage"]), (want, 1 if where[0] == "flutter-commit" else 2), (where, outcome))
        v = self.V(bad={("flutter-area", "s2"): {self.P2P: "fail"}}, outcome={("flutter-area-rr", "2"): "infra_error"})
        self.assertEqual((v["outcome"], v["broken"]), ("infra_error", []))

    def test_forbidden_patch_runs_nothing(self):
        for name, body in (("test", "diff --git a/test/a_test.dart b/test/a_test.dart\n--- a/test/a_test.dart\n+++ b/test/a_test.dart\n@@ -1 +1 @@\n-void main() {}\n+void main() { }\n"),
                           ("config", "diff --git a/pubspec.yaml b/pubspec.yaml\n--- a/pubspec.yaml\n+++ b/pubspec.yaml\n@@ -1 +1 @@\n-name: x\n+name: y\n"),
                           ("garbage", "not a patch\n")):
            pathlib.Path(self.patch).write_text(body); self.calls = []
            v = self.V()
            self.assertEqual((v["outcome"], v["decided_in_stage"]), ("rejected_by_validator", 0), name); self.assertEqual(self.calls, [], name)
        pathlib.Path(self.patch).write_text("diff --git a/lib/a.dart b/lib/a.dart\n--- a/lib/a.dart\n+++ b/lib/a.dart\n@@ -1 +1 @@\n-int g() => 1;\n+int f() => 2;\n")
        self.assertEqual(self.V()["outcome"], "did_not_apply")

    def test_empty_patch_is_run_and_fails_in_stage_1(self):
        pathlib.Path(self.patch).write_text("")
        v = self.V(bad={("flutter-commit", r): {self.F2P: "fail"} for r in "123"})
        self.assertEqual((v["outcome"], v["empty_patch"], v["f2p_failed"], len(v["samples"]), v["decided_in_stage"]), ("not_resolved", True, 1, 3, 1))

    def test_performance_case_is_never_required(self):
        perf = next(iter(host.PERFORMANCE_CASES))
        (TMP / "secret/T0/cases.json").write_text(json.dumps({"f2p": [{"job": "flutter-commit", "case": self.F2P}], "p2p": [{"job": "flutter-area", "case": perf}, {"job": "flutter-area", "case": self.P2P}]}))
        v = self.V(); self.assertEqual((v["outcome"], v["p2p_total"]), ("resolved", 1))


if __name__ == "__main__":
    import warnings; warnings.simplefilter("ignore", ResourceWarning)
    setup(); unittest.main(argv=[sys.argv[0]], exit=False, verbosity=1, warnings="ignore")
    import shutil; shutil.rmtree(TMP, ignore_errors=True)
