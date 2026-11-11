Negative controls for the validator: patches that keep the bug and try to look green.
- `skip-all.diff`: adds a root `conftest.py` that skips every test (accepted by validator v1: "13 skipped", valid).
- `skip-inside-package.diff`: the same hook placed inside the allowed path (`boltons/conftest.py`).
Both must come back `valid: false`.
- `skip-from-library.diff`: stays inside the allowed path and makes the library skip the test module at import. Only
  the "every expected test ran and passed" check can catch this one.
- `exit-code.diff`: applies the real fix, so all 618 tests pass in the report, and makes the test process end with
  exit code 23 after the report is written (accepted by validator v2). Must come back `valid: false`.
