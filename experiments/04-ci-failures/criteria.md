# Case selection criteria (written BEFORE the search, 11/11/2026)

> Translated from the Portuguese original, which is the record (kept in the author's private production repository).
> Dates are day/month, 2026, as in the original. Two edits for the public copy, both marked in brackets: the owner list
> of rule 5 is described generically, and the protocol file's private path is described instead of linked. Nothing
> else was changed, shortened or reworded in substance.

Protocol: the video's protocol file in the private production repository (method closed on 09/11; summarised in
[`README.md`](README.md#method)). This file only details what the protocol leaves open ("medium-sized project", "real
CI failure", "original suite"). Nothing here changes the method.

## Repository
1. Public on GitHub, main language **Go** or **Python** (the API's `language` field).
2. **Medium size:** between 300 and 15,000 stars and repository size (the API's `size`) up to 300 MB.
3. Permissive licence (`license.spdx_id` in MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0).
4. Not archived, not a fork.
5. **Excluded:** [redacted for the public copy: repositories owned by the author's employer and related projects, by
   the model provider (anthropics), and by the author's own accounts]. At most **2 cases per repository**, so the result
   is not concentrated in one project.

## The failure
6. A GitHub Actions run with `event = push` on the **default branch**, `conclusion = failure`, from 2025-01-01 on.
7. The failed job is a **test** job: the name of the job or of the failed step contains `test` (or `pytest`, `unit`),
   and the failed step is not lint, formatting, documentation build, release, coverage, deploy or dependency install.
8. The **fix commit is the next commit** on the default branch (the first commit whose parent is the broken commit),
   and the **same workflow** ends with `success` on that commit.
9. The fix **touches code that is not a test** (at least one file outside `test`/`tests`/`testdata`/`*_test.go`/
   `test_*.py`/`*_test.py`/`conftest.py`), has at most 10 files and 300 changed lines, and does not touch only
   dependencies, lockfile, CI or tool version (that would be "updating the environment", not fixing the code).
10. Changes of the fix commit to test files become the **maintainer's hidden tests** for that case.

## The original suite (the case's test command)
11. Go: `go test` on the packages that contain the tests that failed in the CI log (or `./...` when the log does not
    allow identifying them), with the Go version of `go.mod` (`GOTOOLCHAIN=auto` during preparation).
    Python: `pytest` on the test files that failed in the CI log, with the Python version of the failed job.
    Narrowing the scope to the package/file is necessary because whole suites depend on services (database, network,
    Docker) that the network-less box does not have; the same command applies to the broken commit, the maintainer's
    commit and every attempt.
12. **Reproduction in our box (protocol rule):** the command is run 3 times on the broken commit and 3 times on the
    maintainer's, **without network**, after the dependencies are prepared with network. It enters if the broken one
    fails 3/3 and the maintainer's passes 3/3. Mixed result ⇒ **intermittent** (separate list, with the counts). Does
    not reproduce (the broken one passes 3/3, or the maintainer's fails) ⇒ discarded, with the reason.
13. Each run has a 10-minute timeout; past that ⇒ discarded ("too slow for 3 × 3").

## Order and freezing
14. Candidates are examined in the order the search returns them (repositories by stars, descending; failures from the
    most recent to the oldest). Every examined candidate goes into `mining/candidates.log` with the reason it entered
    or was discarded.
15. ~~The first 30 that pass reproduction form `cases.csv`~~ (replaced on 11/11, see below). `cases.csv` is frozen with
    a sha256 in the repository before v1.

## Amendment of 11/11/2026: number of cases (before any agent attempt)
Decision of Francisco after the reproduction phase, **before the smoke test and before v1**: the search yielded 113
candidates (Go 63, Python 50, from about 700 repositories examined). Of the first 20, only 2 reproduced (about 10%),
which projects about 11 cases, not 30. It is decided:
16. **No widening of the search.** The case set is **every** candidate among the 113 already mined that passes rule
    12, with no choice and no cut (the "2 per repository" of rule 5 still applies). The number N is only known after
    the 113 are processed, and no agent attempt runs before that.
17. **Floor: N ≥ 8.** If fewer than 8 reproduce, the search is widened with the same criteria (more star and date
    ranges), and the first complete batch that brings N to 8 or more closes the set.
18. **N_REP = 3** per case and per version, unchanged; budget unchanged (US$ 0.33 per attempt, US$ 30 per version).
19. The video states the **funnel** (repositories examined → candidates → reproduced, with the count of each discard
    reason) and the selection bias: only failures that reproduce in a box without network and without services get
    in, which favours self-contained failures.
20. The smoke test (2 attempts, on the first 2 reproduced cases) measures cost; it does not count as v1 data and stays
    in `smoke/`.

## Amendment of 12/11/2026: the gateway's reservation (before any v1 attempt)
Decision of Francisco, after the smoke test and **before the first v1 attempt**; it applies equally to v1 and v2.
21. **The gateway's input estimate: request bytes ÷ 2** (was ÷ 1), and **the agent's `max_tokens`: 4,096** (was
    8,192). Reason: in the smoke test the reservation of a single call went past US$ 0.33 once the conversation went
    beyond about 95 KB, while the real cost per call stayed around US$ 0.01 (maximum observed US$ 0.0099). With ÷ 1, long
    attempts would be stopped by the estimate, not by spending. Cap per attempt (US$ 0.33) and per version (US$ 30)
    unchanged. The gateway still stops if a call costs more than its reservation. Offline gateway test re-run: 13/13.

## Amendment of 12/11/2026: candidate anacrolix/torrent `23d8abf9` (before any v1 attempt)
22. This candidate had been discarded during preparation because of an error in our tooling (`chmod` on the Go
    module cache, fixed later), not because of the case. It was repeated on its own, with the fixed tooling, before any
    v1 attempt and under the same rule 12: the broken commit failed 3/3, but **the maintainer's fix also failed 3/3**
    in our box. It does not reproduce; the set stays at **11 cases** (Go 7, Python 4) and `cases.csv` does not change
    (sha256 `d0abec78…a5b8`).
    Note: the amendment of 11/11 says "Go 63, Python 50"; the correct split of the 113 candidates is Go 72, Python 41.

## Amendment of 12/11/2026: the v2 change (before any v2 attempt)
23. Decision of Francisco after seeing v1: v2 differs from v1 in **a single instruction** added to the agent's system
    prompt, before the final instruction: "Before you finish, write down the root cause of the failure and check that
    your change fixes that cause, not just the assertion that failed. If you can't, stop and say so." Everything else
    stays the same: model, tool, limits (25 min, 60 tool calls), gateway, `max_tokens` 4,096, estimate bytes ÷ 2,
    US$ 0.33 per attempt and US$ 30 per version; same 11 cases, 3 repetitions, same order and same executor. The
    prompts of the two versions are in `agent/prompt-v1.txt` and `agent/prompt-v2.txt` (v1's reproduces byte for byte
    what ran).

## Amendment of 12/11/2026: two cases out of the main analysis (AFTER the v1 and v2 collection, before opening the judging key)
24. A finding after the collection, in a blind review of the packets by a second model (Codex,
    `results/blind/codex-review-2026-11-12/`), checked against the maintainers' diffs: in two of the 11 cases the
    maintainer's fix **does not touch production code**, which is what rule 9 requires.
    - **nkanaev/yarr:** the fix changes only `src/parser/fixtures/atom/link-in-id.xml`, test data. Our list of test
      patterns did not have `fixtures/` (the same class of gap as the osv-scanner snapshot, found before v1).
    - **boyter/scc:** outside the test file, the fix changes only a comment in `processor/counters_notokens.go`
      ("thirty-two" → "thirty-three"); the real change is the test's expectation.
    In both, the maintainer fixed the test. An agent forbidden to touch tests can only make it green by changing the
    code to meet an outdated expectation. Decision of Francisco (12/11), **taken without opening `key.jsonl`**: the two
    leave the **main analysis**, which keeps **9 cases** (Go 5, Python 4; floor of 8 respected); `cases.csv`, the raw
    results and the packets stay as they are, and the two cases are counted **separately** in the video ("2 of 11 red
    builds were an outdated test"). From what was already public per case before the key, the exclusion does not favour
    either version: yarr had the same outcome in all 6 attempts; scc had a budget stop in 5 of 6.
    Rule 9 is from now on read like this for all: "code that is not a test" means an **executable** change outside
    tests, fixtures, snapshots, golden files and test data; a comment-only change does not count. The other 9 cases are
    re-checked under this reading (record in `cases/eligibility-audit.md`).
25. **Second opinion in the judging.** The verdicts are still Francisco's, blind as to the version. The Codex review
    appears on the judging page as a second opinion (verdict and note), and each recorded verdict records that it was
    visible. The video says so. New checks suggested by that review only count as evidence after they are run in our
    box (Kata, no network); no third-party repository runs on the Mac.

## Amendment of 12/11/2026: judging delegated to Codex (before opening the key)
26. Francisco explicitly delegated the remaining decisions to Codex: "julga e decidi por mim esses ja" ("judge and
    decide these for me now").
    The records made under this delegation get `source=codex_delegated`, `reviewer=Codex` and `user_delegated=true`,
    keeping the note and the record that the second opinion was visible. For these records, this replaces the
    attribution to the human judge of amendment 25: they are not an independent human assessment, nor a second
    independent assessment by the same model. Later clicks by Francisco are still identified as human and the history
    is kept. The version key stays closed; exclusions and automatic rules stay in force. The new gobwas/ws probes only
    support the judging after the in-box check required by amendment 25.

## Amendment of 12/11/2026: QuantDinger out of the main analysis (after the collection, before opening the key)
27. The audit in the box (`cases/eligibility-audit.md`, `results/probes/quantdinger/`, `results/hidden-logs/`) showed
    that the case OpenByteInc/QuantDinger is of the same kind as yarr and scc: the test that failed in CI
    (`tests/test_live_order_support.py`, `assert len(calls) == 4`) was fixed by the maintainer **in the test itself**
    (`assert calls`); the broken commit plus only that test change already passes the case's command. The code the same
    commit changes (`bitget.py`) deals with something else. The hidden test on which all 6 attempts "failed"
    (`test_live_exchange_fees.py::test_exchange_funding_payments_use_signed_cash_flow`) belongs to that other change and
    **fails in the same way without any agent patch**; it does not measure the fix. By the letter of rule 9 the case
    passed (there is an executable change outside tests); by the reason of amendment 24 (the maintainer fixed the
    test, not the code), it did not.
    Decision of Francisco (12/11), **without opening `key.jsonl`**: QuantDinger leaves the main analysis, which keeps
    **8 cases** (Go 5: ws, cosign, minify, mcp-go, miniredis; Python 3: ludwig, pyinfra, scrapy-redis), exactly at the
    floor of the amendment of 11/11. QuantDinger's 6 "worse by rule" no longer count; raw data and packets stay as they
    are. Separately, the video says: **3 of 11 red builds were fixed by the maintainer by changing the test**. The
    exclusion does not favour either version (same outcome in all 6 attempts).
    Limits the video states: (a) the extra gobwas/ws tests were written by the second reviewer after reading the
    patches (three use cases, with the maintainer's control passing); (b) for gobwas/ws the judging was not fully blind,
    because the table of outcomes per case and per version was already known and allows deducing which version the two
    patches that passed the hidden tests came from.

## Amendment of 13/11/2026: what counts as a budget stop and what is an infrastructure failure (after the collection; future runs only)
28. **In the collection** the agent recorded any 429 from the gateway as `budget_exhausted`: an attempt, counted, with
    whatever was in the working copy validated. That covered three different things: the attempt's own cap (US$ 0.33),
    the version's total cap (US$ 30) and a rate limit from the provider. In the archived rounds only the first one
    happened: the 5 budget stops (3 in v1, 2 in v2) were all the attempt's own cap, and each version spent about
    US$ 2.5 of its US$ 30. No archived attempt changes under this amendment.
    **From now on:** (a) only the attempt's own cap is `budget_exhausted`, an outcome of the attempt. (b) The version's
    total cap, a provider rate limit or error, a halted gateway, a closed run or a lost connection is
    `gateway_unavailable`: not an attempt. Nothing is validated, the try is kept in `results/infra-<round>.jsonl`, the
    round stops, and the case/repetition is redone under a new run id (at most 3 tries, then a person decides). So when
    the total cap is reached the round **stops and asks for a person** instead of recording the remaining attempts as
    budget stops; raising the cap or ending the round there is a decision to be written down, not a default.
    (c) `gateway_unavailable` is reported by the agent's pod, which ran commands a model chose. It is accepted only
    when something outside the pod agrees: the gateway booked at least one failed model call to that run, or the
    runner's own close of the run was never confirmed. Without that, the try **is** an attempt: it is recorded as an
    error, without a patch, and is not redone. A lost connection the gateway never saw falls here on purpose: the
    harness prefers to count a doubtful try rather than let the pod void one.
    Also from now on the agent's shell is not a login shell (`bash -c`, not `bash -lc`): in the collection the login
    shell dropped the Go directory from `PATH`, so the first `go` command of an attempt answered 127 and the agent
    spent a call fixing it, in both versions alike. A new collection therefore differs from the archive in this, and
    its tool-call and cost figures are not comparable to the archived ones without saying so.
