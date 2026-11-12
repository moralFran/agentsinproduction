# Eligibility audit of the 11 cases (12/11/2026, after the collection)

> Translated from the Portuguese original.

Rule 9 as amendment 24 reads it: the maintainer's fix must contain an **executable change outside** tests, fixtures,
snapshots, golden files and test data; a comment-only change does not count. Source: each case's `fix.diff` (the diff
between the broken commit and the fix commit), read file by file. Nothing was re-run or re-classified here.

| Case | Files of the fix | Test / test data | Executable change outside tests? | Rule 9 |
|---|---|---|---|---|
| alicebob/miniredis | `db.go`, `cmd_string_test.go`, `integration/generic_test.go`, `integration/string_test.go` | the 3 `_test.go` | yes: `db.go` (new condition, 2 lines) | passes |
| boyter/scc | `processor/counters_notokens.go`, `processor/counters_notokens_test.go` | the `_test.go` | **no**: in `counters_notokens.go` only 4 comment lines change ("Thirty-two… 366" → "Thirty-three… 367") | **does not pass** (amendment 24) |
| gobwas/ws | `wsflate/writer.go`, `wsflate/writer_test.go` | the `_test.go` | yes: `writer.go` (23 lines of code) | passes |
| ludwig-ai/ludwig | `ludwig/data/dataset/ray.py` | none | yes | passes |
| mark3labs/mcp-go | `client/transport/streamable_http.go`, `server/server.go`, `server/server_test.go` | the `_test.go` | yes: the two production `.go` files | passes |
| nkanaev/yarr | `src/parser/fixtures/atom/link-in-id.xml` | the fixture (only file) | **no** | **does not pass** (amendment 24) |
| OpenByteInc/QuantDinger | `app/services/live_trading/bitget.py`, `requirements.txt`, `requirements.lock`, `tests/test_live_exchange_fees.py`, `tests/test_live_order_support.py` | the 2 `tests/`; the 2 `requirements` are dependency files | yes: `bitget.py` (19 lines) | passes **by the letter**; see the caveat |
| pyinfra-dev/pyinfra | `src/pyinfra/api/facts.py` | none | yes | passes |
| rmax/scrapy-redis | `src/scrapy_redis/spiders.py`, `tests/test_spiders.py` | the `tests/` | yes: `spiders.py` (1 line) | passes |
| sigstore/cosign | `pkg/oci/remote/write.go`, `pkg/oci/remote/write_test.go` | the `_test.go` | yes: `write.go` | passes |
| tdewolff/minify | `svg/pathdata.go`, `svg/pathdata_test.go`, `svg/svg_test.go` | the 2 `_test.go` | yes: `pathdata.go` | passes |

Result: apart from `yarr` and `scc` (already handled in amendment 24), **no other case fails rule 9 as written**.

## Caveat: QuantDinger passes by the letter, but the code change does not address the original failure
Evidence measured in the box (executor pods, Kata, no network; `results/probes/quantdinger/`):
- The test that failed in CI and became the case's command is `tests/test_live_order_support.py::
  test_all_worker_client_order_id_calls_match_helper_signature` (`assert len(calls) == 4`).
- The maintainer's fix for **that** test is a change **in the test**: `assert len(calls) == 4` → `assert calls`. Broken
  commit + only that test change: the case's command passes (24 passed) — `qd-a`.
- The maintainer's code change (`bitget.py`) belongs to **another** test, `tests/test_live_exchange_fees.py::
  test_exchange_funding_payments_use_signed_cash_flow` (Bitget parameter), which **already failed on the broken commit**
  in our box (`qd-d`: 1 failed, 28 passed) and was not part of the case's command.
In other words: in substance it is the same situation as `yarr` and `scc` (for the original failure, the maintainer fixed
the test), but rule 9 as written is satisfied because the same commit carries an unrelated executable change. The
decision is Francisco's; nothing was changed because of this.

[Note added to the public copy: the decision was taken afterwards as amendment 27 in [`criteria.md`](../criteria.md);
QuantDinger left the main analysis.]
