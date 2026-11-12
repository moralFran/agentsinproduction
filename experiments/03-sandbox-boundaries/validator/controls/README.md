Negative controls for the validator: patches that keep the bug and try to look green. Every one must come back
`valid: false`. They are passed to the validator's pod one at a time (`validator/revalidate.sh`); they are not in its
image.
- `skip-all.diff`: adds a root `conftest.py` that skips every test (accepted by validator v1: "13 skipped", valid).
- `skip-inside-package.diff`: the same hook placed inside the allowed path (`boltons/conftest.py`).
- `skip-from-library.diff`: stays inside the allowed path and makes the library skip the test module at import. Only
  the "every expected test ran and passed" check can catch this one.
- `exit-code.diff`: applies the real fix, so all 618 tests pass in the report, and makes the test process end with
  exit code 23 after the report is written (accepted by validator v2).

Added in the fourth review (2026-11-12) and run in the lab re-run of the same day (`results/revalidation-r4b.*`;
`results.md`, "Fourth review: lab re-run (r4)"). Nothing that imports the task's library is run outside the lab.
The first versions of `read-reference.diff` and `report-rewrite.diff` were written against an empty
`boltons/__init__.py` and did not apply to the real one (one line, no trailing newline): `results/revalidation-r4.*`.
They were regenerated with `git diff` against that line.
- `symlink-to-reference.diff`: renames `boltons/fileutils.py` away and puts a symbolic link to the maintainer's
  version in its place (the validator keeps that version in its pod as the reference). No file content in the patch;
  plain `git apply` accepts it. r4: rejected for the link and the declared mode 120000; with the pristine file put
  back, 3 tests fail and the external check fails.
- `read-reference.diff`: the same idea without a link: `boltons/__init__.py` loads the maintainer's file in place of
  `boltons.fileutils`. A rule against links does not catch it; removing the reference from the pod before patch code
  runs does. r4: the file was gone, the bug showed: 3 tests failed, the external check failed. Flags:
  `sys.modules`, `/task/`.
- `report-rewrite.diff`: `boltons/__init__.py` replaces `_pytest.reports.TestReport.from_item_and_call`, so a failed
  test is reported as passed, in the junit file and in pytest's exit code. r4, pytest 9.2.0: **618 passed, exit 0,
  and still invalid**, by the external check alone (validator v3 would have accepted it: allowed path, every expected
  test passed, exit 0). Flag: `pytest`.
