# Post-collection audit (12/11/2026): hidden-test logs and probes

> Translated from the Portuguese original.

Everything here ran in executor pods (Kata, no network) on `aip-ci-01`, with `cases/audit.py` (the executor's `run`
mode: applies an optional patch and, if asked, the maintainer's test changes; runs a command; prints the output). It
classifies nothing. `results/hidden-logs/<run>.log`: output of the maintainer's hidden tests for each green attempt
that failed them (11).

## 1. What fails in the hidden tests
| Case | Attempts | Hidden test that fails | Does it exercise the cause of the original failure? |
|---|---|---|---|
| QuantDinger | v1 r1–r3, v2 r1–r3 (6) | always the same one, 1 of 53: `test_live_exchange_fees.py::test_exchange_funding_payments_use_signed_cash_flow[…Bitget…]` | **No.** It is another test, from another change in the same commit (`bitget.py`). The agent's patches touch `pending_order_worker.py` / `close_reconciliation.py` / `live_order_support.py`. |
| gobwas/ws | v1 r1–r3, v2 r1 (4) | `TestWriterClose` (subtests "flushed" in v1 r1 and r2; "not flushed" in v1 r3 and v2 r1) and `TestWriterCloseFlate` | **Yes.** They are the maintainer's new tests for `wsflate.Writer.Close`, the same code as the original failure. |
| boyter/scc | v2 r3 (1) | package `processor` fails; **the test's name did not make it into the log** (the output is flooded with TRACE lines and only the last 120 KB were kept) | The maintainer's test change expects 33 languages without tokens, including "Txtar" (was 32); the agent's patch touched `languages.json` and `processor/constants.go`. Inferred from the diff, not from the log. |

### QuantDinger, isolated (`results/probes/quantdinger/`)
| Run | Tree | Command | Result |
|---|---|---|---|
| `qd-a` | broken + only the maintainer's change to the original test (`assert len(calls) == 4` → `assert calls`) | the case's command | 24 passed |
| `qd-b` | broken + the maintainer's tests, **without** the code change | hidden command | 1 failed (the Bitget test: 4 records instead of 1), 52 passed |
| `qd-c` | broken + only the maintainer's `bitget.py` + the maintainer's tests | hidden command | 53 passed |
| `qd-d` | broken, untouched | `tests/test_live_exchange_fees.py` | 1 failed (the Bitget test), 28 passed: **it already failed before** |
| `qd-e` | prepared environment | installed versions | pillow 13.0.0, pypdf 6.21.4, certifi 2026.10.23 |

- The hidden test that fails **fails the same way without any patch** (`qd-b`) and only passes with the `bitget.py`
  change (`qd-c`).
- It needs no new dependency: it passes in the environment prepared at the broken commit (which already had versions
  that satisfy the new `requirements`, because the preparation installed the latest ones).
- For the original test, the maintainer's minimal fix is the change in the test itself (`qd-a`).

### scc, isolated (`results/probes/scc/`)
`scc-a`: broken commit + only the maintainer's test changes, no code change → the `processor` package passes. The
maintainer's fix is the test change (the production `.go` only changes a comment).

## 2. The second reviewer's probes for gobwas/ws (`results/probes/ws/`)
File `results/blind/codex-review-2026-11-12/writer_review_test.go` (standard library only), copied into `wsflate/` and
run with `go test -count=1 -v -run TestReview ./wsflate`. The agent's 6 patches are all different from each other.

| Tree | Maintainer's hidden tests (collection) | CloseEmptyMessage | WriteAfterFlush | RejectBadEmptyCompressor |
|---|---|---|---|---|
| broken commit | — | FAIL | FAIL | pass |
| **maintainer's fix (control)** | passes | **pass** | **pass** | **pass** |
| v1-e88f0806-r1 | failed | pass | pass | pass |
| v1-e88f0806-r2 | failed | pass | pass | pass |
| v1-e88f0806-r3 | failed | FAIL | FAIL | FAIL |
| v2-e88f0806-r1 | failed | FAIL | FAIL | pass |
| v2-e88f0806-r2 | **passed** | pass | **FAIL** | pass |
| v2-e88f0806-r3 | **passed** | **FAIL** | pass | **FAIL** |

Failure texts:
- **WriteAfterFlush** (v1 r3, v2 r1, v2 r2): `wire=4acb2c2a2e0100 decoded="first" error=<nil>; want="firstsecond" without error`.
  `Write("first")`, `Flush()`, `Write("second")`, `Close()`: `Close` returns `nil` and what was written after the
  `Flush` disappears, with no error.
- **CloseEmptyMessage** (v1 r3, v2 r3): `wire= decoded="" error=flate: corrupt input before offset 5`: closing an empty
  message emits nothing and the reader reports corrupt input. In v2 r1: `Close` returns `bad compressor: unexpected stream tail`.
- **RejectBadEmptyCompressor** (v1 r3, v2 r3): `Close accepted a compressor that never emits a sync-flush marker`.
- On the broken commit the first two fail with `bad compressor: unexpected stream tail` (the original defect).

The control holds: the maintainer's fix passes all three. **Two patches that passed the maintainer's hidden tests
(v2 r2 and v2 r3) fail the probes**; in v2 r2 the failure is silent data loss. Limit: the probes were written by the
second reviewer after reading the patches; they are three use cases, not a suite.

## 3. The pyinfra probe: not run
It would need a new test with `host` and `_handle_fact_kwargs` mocked by us (the reviewer itself ran it with mocks); per
the instruction not to invent mocks, it stays out.

Captures: `capture/casts/v5-probe-fixed.cast` (control), `v5-probe-patch-r2.cast`, `v5-probe-patch-r3.cast`.
