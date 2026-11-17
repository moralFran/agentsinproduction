# Experiment 05 · one agent × a team (V6, A-v07) · criteria

> Translated from the Portuguese original, which is the record (kept in the author's private production repository).
> Dates are day/month, 2026, as in the original; times are as in the original (UTC, or BRT where marked: Brasília
> time). Numbers use English separators (1,306; US$ 0.75). Edits for the public copy, each marked in square brackets:
> the app's private repository, files of the private production repository outside this experiment folder (the video's
> narration script, its capture folder, the cost ledger) and paths on the author's external disk are described instead
> of named; short commit hashes of the private repositories are replaced by a description of the commit; the name of
> one app test case is omitted. Where the harness refers to the Firebase emulator projects, the public code uses
> `app-test`, `app-rules-test` and `demo-app-e2e-fn` in place of the private ids (this file names none of them).
> `tasks/` is the private analysis folder (it holds the app's code and is not published). "The script" is the video's
> narration script, whose "Protocol" section is the method. Francisco's words, and the agent's question to him, are
> kept in Portuguese with a translation in parentheses. Nothing else was changed, shortened or reworded in substance.

Protocol approved by Francisco: [the video's narration script, in the private production repository], section
"Protocol" (draft 4, 12/11/2026).
This file records what was closed **before the collection** and each amendment, with its date. Nothing here was written
after seeing an agent's result.

## Closed on 15/11/2026 (before any run)

1. **Cap (Francisco, 15/11):** at most **US$ 15 of model calls for the whole experiment**, quote included. The
   gateway's total budget is US$ 15. The per-attempt limit comes out of the quote; if the 48 attempts do not fit, the
   options go to him before running. Model: Sonnet 5.5 (his decision of 09/11).
2. **Source:** the app in [the app's private repository], read-only. The snapshots come from `git archive <parent commit>`;
   nothing is changed there. The app's code, paths and names stay out of the public repository (analysis in `tasks/`,
   private).
3. **The 8 tasks** are those of the script's table. The static analysis of 15/11 (`tasks/analysis.md`) did not swap
   any; a swap only happens if the owner's fix does not reproduce in the box (rule 4 of the script), and the video says
   how many were swapped.

## Amendments of 15/11/2026 (after the static analysis of the 8 commits, before the box existed)

The analysis showed things the script did not foresee. Each rule below applies to both setups and was written without
any agent result.

- **E1 · Tests that must start passing and tests that must keep passing.** "The commit's tests fail 3/3" and "the
  area's suite passes 3/3" are now measured per **test case**, in the box:
  - *must start passing* (F2P): cases from the commit's test files that fail 3/3 on the snapshot with the commit's
    tests applied and pass 3/3 with the owner's fix applied;
  - *must keep passing* (P2P): cases from the suite of each area touched by the commit that pass 3/3 on the snapshot
    with the commit's tests **and** 3/3 with the owner's fix.
  A case that already fails on the snapshot and keeps failing with the owner's fix (a test broken before, or broken by
  what the snapshot removes) stays out of both lists. An unstable case (mixed result in 3 + 3 runs) also stays out and
  is counted. A task needs at least one F2P case; if it has none, it is swapped.
  Reason: in task 7 the commit's 3 Jest files have no code change behind them (only the Dart test can fail on the
  parent); in task 3 one of the commit's Dart tests is already red on the parent; and there are tests that read files
  the snapshot removes.
- **E2 · Required checks of an attempt:** the validator outside the agent rejects a patch that touches tests, CI or
  configuration (`pubspec.yaml`, `package.json`, locks, `firebase*.json`, `analysis_options.yaml`, `.github/`,
  `Makefile`); then, all F2P cases and all P2P cases pass 3/3. Failed any of them ⇒ not a fix.
- **E3 · Area of a commit:** rules (rules tests in the emulator), functions (Jest of the functions folder) and Flutter
  (`flutter test`). An area's suite only enters if the commit has a code file (not a test file) in that area. If the
  time measurement in the box shows that 3 runs of the whole suite per attempt do not fit, the reduction is a new
  amendment, written before the quote and shown to Francisco.
- **E4 · What the snapshot does not take** (besides what the script already lists): `CLAUDE.md`, `AGENTS.md`, the whole
  of `docs/` (plans, technical debt and runbooks: two documents describe the fixes of tasks 1 and 3), `gcp/`, `ops/`,
  `dev-env/`, `load-tests/`, `.github/`, `.vscode/`, `.firebase/`, `.gitleaks*`, `scripts/security/`, `scripts/tests/`,
  `integration_test/tool/`, `perf_report.html`, the Firebase client configuration files (`google-services.json`,
  `GoogleService-Info.plist`) and `lib/internal/firebase/.firebaserc`. Tests that depend on these files leave the lists
  by rule E1. The owner's fix is applied **without** the commit's `docs/` files.
- **E5 · Version change in `pubspec.yaml`** (tasks 5 and 7): no test depends on it; its absence does not count against
  the agent and the agent's patch may not touch the file (E2).
- **E6 · Dependencies:** `pubspec.lock` is not versioned in the app and two git dependencies have no fixed ref. The box
  resolves the dependencies once (Flutter 3.41.9, Node 20, Java 21, a fixed version of firebase-tools with the emulators
  already downloaded) and the generated locks are kept with the image; all attempts use the same resolution. The box
  has no network: everything is installed in the preparation.
- **E7 · Clock:** server tests use dates from 08/01/2027 on as the future; the collection runs before that.
- **E8 · Task 1** stays as the trivial control task (one rule line), as in the approved table.

## Amendment of 15/11/2026 (Francisco, while the box was being assembled, before any model call)

- **E9 · Performance tests are not run** ("os testes de performance nao sao para serem executados" ("the performance
  tests are not meant to be run")). They stay out of everything, in both setups: the performance journeys of
  `integration_test/` (`make test-perf*`), the k6 load tests (`load-tests/`, `make test-k6-*`) and the performance
  workflow. The harness never runs them: the Flutter suite is `flutter test` in `test/` (the app's own Makefile leaves
  `integration_test/` out of the unit tests), the functions suite is what `npm test` runs, and the box has no device,
  no k6 and no network. None of their cases enters an F2P or P2P list. The project notes given to the agent
  (`agent/project.txt`, the same in both setups) say not to run them.

## Amendment of 15/11/2026, evening (time measurement in the box; approved by Francisco: "Pode ser" ("That works"); before any model call)

- **E10 · Validation in two stages** (the reduction E3 foresaw; replaces "all P2P pass 3/3" of E2).
  Measured in the box: the Flutter suite takes about 10 min (4 CPUs) and the functions suite about 13 min across 3 pods
  (6 CPUs). Three runs of the whole suite per attempt would mean about 19 h of machine time for validation alone for
  the 48 attempts.
  - *Stage 1, every attempt:* path validator (E2) and the commit's test files, 3 runs. All F2P cases pass 3/3 and the
    P2P cases of those files pass 3/3. Failed ⇒ not a fix, and stage 2 does not run.
  - *Stage 2, only for those that passed stage 1:* the suite of each in-scope area (E3), **1 run**. Each test file
    with a P2P case that failed (or that did not load) is run 2 more times. A P2P case counts as **broken** if it fails
    in the first run and in at least one of the two repetitions; if it passes in both repetitions, it is counted as
    unstable in that attempt, appears in the report and does not count against the patch. Any broken case ⇒ not a fix.
  - Applies equally to both setups and to the controls (owner's fix and empty patch) of each task.
  - Accepted limit: a case that the patch makes fail only now and then can pass in the single run of stage 2.
- **Machine during the collection (Francisco, 15/11, same answer):** the same VM goes from 8 to 32 vCPUs only during
  the collection and the validation (same disk, same image, same snapshots and same dependencies). The CPU and memory
  limits of each pod do not change; what changes is how many pods run at the same time. The two setups run interleaved
  in the order of `order.csv`.

## Amendments of 15/11/2026, 23h30 BRT (record of what assembling the box required)

Everything below was **implemented before any model call** (the first was a pipeline test on task 1, at 19h51 BRT on
15/11; the files have an earlier date). The text was written after that test and during the quote of task 2; no rule
changed because of them. Applies equally to both setups and to the controls.

- **E11 · One pinned dependency (deviation from E6).** The clean resolution of 15/11 picks
  `connectivity_plus_platform_interface` 2.1.0, published on 30/03/2026, and with it the app does not compile on the
  parent commits nor with the owner's fix (a `switch` is no longer exhaustive; in a partial run of task 4, 13 of the
  first 28 test files did not compile). The app only handled the new value on 27/10/2026, after the 8 commits. The box
  pins **2.0.1**, the version the owner's old lock had; it is the only difference from the clean resolution. Evidence
  and method in `infra/locks/README.md`; both locks (with and without the pin) are kept. Nothing is added to the
  snapshot.
- **E12 · What the box adds around the snapshot.** An empty directory `admin-scripts/dashboard` (Jest refuses to start
  without it, because it is the root of a Jest project and E4 removes the folder); `node_modules` enters as a link to a
  read-only set; the working copy is in memory; `HOME=/home/agent`, UTC time zone, `CI` not defined.
- **E13 · The path validator rejects more than E2 lists:** besides E2's list, other CI folders (`.circleci/`,
  `.gitlab/`, `.buildkite/`, `.woodpecker/`), `pubspec_overrides.yaml`, `.firebaserc`, `dart_test.yaml`,
  `jest.config.*`, `.fvmrc`, `.npmrc` and the other locks (`yarn.lock`, `pnpm-lock.yaml`, `npm-shrinkwrap.json`,
  `Podfile.lock`, `Gemfile.lock`). These are files that change what the tests run. `vendor/` is allowed (it is code).
  The notes given to the agent (`agent/project.txt`) list the same files.
- **E14 · How the suites run.** The commit's tests and the area's suite are separate jobs. The Flutter suite runs in 4
  processes inside one pod; the functions suite, split across 3 pods, one Jest process per file. The "functions" area
  is what `npm test` runs. Of the functions end-to-end tests (`tests/e2e-functions`), only the commit's own file runs:
  task 8's came out unstable (one run hung for 900 s), which removed 2 cases that would be F2P; task 7's Jest stays out
  of scope, as E1 already foresaw.
- **E15 · Cases with time.** A case that measures execution time ([the app test case's name omitted]) ran in 3 initial
  samples, before E9; since 16h14 BRT it is skipped by name and is in no list. Five other cases with a time limit
  stayed, classified as functional (the time is a condition of the tested behaviour, not a performance measure); they
  are named in `tasks/repro-report.md`.
- **E16 · Possible validator results:** `resolved`, `not_resolved`, `rejected_by_validator`, `did_not_apply`,
  `test_changed_tree`, `timeout`, `infra_error`. Only `resolved` counts as a fix. `infra_error` and `timeout` are not a
  verdict the first time: the validation is redone **once** on the same saved patch (the agent does not run again). A
  second `timeout` counts as not a fix (a patch can hang the tests). A second `infra_error` is investigated and appears
  in the report; the attempt is only left without a verdict if the cause is in the box, and the video says so.
- **E17 · Lists closed** (`tasks.csv`, 02:10 UTC on 16/11, 168 reproduction samples): all 8 tasks reproduce and have an
  F2P case; none was swapped. F2P / P2P per task: T1 3 / 1,306; T2 4 / 10,566; T3 861 / 5,344; T4 24 / 5,009; T5 19 /
  5,300; T6 12 / 2,749; T7 8 / 5,403; T8 204 / 13,145. Unstable cases out of the lists: 1 in task 2 and 15 in task 8
  (13 of them from the end-to-end file). Leak audit: no identifier that exists only in the owner's fix appears in a
  snapshot or task statement. Each snapshot's hash is in `tasks.csv`.
- **Time of each suite (E3):** Flutter 425 to 713 s per run; functions 2,017 to 2,747 s summing the 3 pods; rules
  123 s. A validation of the 8 tasks costs 159 CPU-min in stage 1 and 494 in stage 2.

## Amendment of 16/11/2026, 00h40 BRT (finding from task 3's control; before any attempt of the experiment)

- **E18 · Control at the same hour (completes stage 2 of E10).** Task 3's control gave "not resolved" **with the
  owner's fix**: a functions P2P case failed in the single run and in both repetitions. The same case failed, at the
  same hour, in the validation of the quote attempt of task 2. Cause: the test writes 4 activities "60 minutes ago" and
  expects them to count as "today" in the São Paulo time zone; between 00h and 01h Brasília time (03:00 to 04:00 UTC)
  they fall on the previous day and the test fails with any code. The reproduction samples ran between 17:30 and 02:10
  UTC and did not hit that window; there may be other cases like this at other hours.
  New rule, the same for both setups and for the controls: a P2P case that failed in the single run and in at least
  one of the two repetitions runs **once with the owner's fix, at the same hour** (only its file). If it also fails
  with the owner's fix, it depends on the clock or on the box and not on the patch: it is counted as
  *environment-dependent*, appears in the report and does not count against the patch. If it passes with the owner's
  fix, it runs once more with the patch, after the control: it is only **broken** if it fails again; if it passes, it
  is unstable in that attempt.
  The lists in `tasks.csv` do not change. Task 3's control is redone with this rule, and the old result is kept as
  `T3-gold.before-E18.json`.
  Accepted limit: a patch that breaks a case only at the hours when the owner's fix also fails is not detected.

## Amendment of 16/11/2026, 07:50 UTC (Francisco's decision on the options from the quote: "ok pode ir" ("ok, go ahead"); before any attempt of the experiment)

- **E19 · Per-attempt limit and number of repetitions (deviation from the script, which foresaw 3 fixed
  repetitions).** The 48 attempts do not fit with certainty in the US$ 14.27 left of the cap without a per-attempt limit
  that would cut off the team (US$ 0.29 for 3 repetitions, US$ 0.44 for 2; the team spent US$ 0.31 on task 2 of the
  quote, and tasks 3 and 8 are bigger). Of the three options shown, he chose this one:
  - **Per-attempt limit: US$ 0.75**, the same for both setups and summing all the team's agents. The gateway reserves
    the worst case of each call before sending it, so an attempt stops US$ 0.12 to US$ 0.20 before the limit.
  - **Repetitions: one at a time, in the order of `order.csv`** (each repetition is a block with the 16 combinations of
    task and setup). Repetition 1 always runs (16 × 0.75 = US$ 12 fits in the balance). The next repetition only starts
    if the gateway's balance is at least **1.25 times the cost of the most expensive complete repetition so far**. The
    cost of a repetition is what the gateway recorded between its start and its end, including attempts that did not
    become a record because of an infrastructure failure. At most 3 repetitions. The decision is taken once, before the
    block's first attempt, and is written to `results/budget-<round>.jsonl` (`cases/budget_gate.py`, called by
    `cases/run_team.sh`).
  - **The number of repetitions is decided only by the balance**, never by results: the rule does not read any
    attempt's verdict.
  - **Incomplete repetition:** if the total cap stops the gateway in the middle of a block, the whole block stays out
    of the comparison (both setups lose the same tasks), its spending enters the total cost and the video says so.
  - The video says how many repetitions were run; "three runs each" only stays in the text if there were 3.
  - The US$ 15 cap does not change (the gateway's total budget, quote included).
- **Machine during the collection:** 32 vCPUs and 128 GB (n2-standard-32), as foreseen on 15/11. The CPU and memory
  ledger goes from 8 CPUs / 26 GiB to 32 CPUs / 104 GiB and `/dev/shm` from 28G to 112G; the limits of each pod do not
  change. Up to 4 attempts open at the same time (`run_team.sh <round> 4 3`), 4 validation jobs per attempt.

## Record during the collection, 16/11/2026, 08:25 UTC (written AFTER seeing the first 4 attempts; no rule changes)

- **Correction of a number in E19.** E19 says that an attempt stops "US$ 0.12 to US$ 0.20 before the limit". That came
  from the quote (calls of up to 21 thousand tokens) and is wrong for a long conversation: a call's reservation grows
  with the size of the request (bytes ÷ 2, all at the cache-write price). In attempt `c1-t8-a-r1` the single agent
  stopped with US$ 0.4244 spent because the next call reserved US$ 0.3409 and US$ 0.3256 was left.
- **Limit this creates in the comparison:** the dollar limit is the same, but it acts on the reservation, and the
  reservation weighs more in a single long context than in separate contexts. In practice the single agent reaches the
  limit with less real spending than the team. The rule stays as it was closed (changing it now would be changing it
  after seeing results); the report and the video say, per attempt, how much was really spent when the limit stopped
  the agent.
- In the same task, the team (`c1-t8-b-r1`) stopped by `stopped_max_tokens` (one response hit the maximum of 4,096
  output tokens per call, a gateway limit equal for both setups) with US$ 0.3115 spent.

## Incident of 16/11/2026, 08:27 UTC: the provider account ran out of credit in the middle of repetition 1 (collection stopped; Francisco's decision pending)

Facts, taken from the gateway log and the journal (`results/attempts-c1.jsonl`, 16 lines):

- At 08:27:12 UTC, with US$ 3.1928 on the gateway's meter, the provider started answering 400 "Your credit balance is
  too low" to every call. There were 14 refusals in a row and no call accepted afterwards.
- **6 attempts of repetition 1 finished before that** and count: T6-A, T5-A, T4-A and T3-B (`resolved`); T8-A
  (stopped by the per-attempt limit) and T8-B (stopped by response size), `not_resolved`.
- **2 attempts were interrupted in the middle:** T4-B with US$ 0.2568 spent (`not_resolved`) and T7-B with US$ 0.4614
  (the patch was already done and gave `resolved`).
- **8 attempts never got to run** (the first call was already refused, US$ 0): T1-A, T1-B, T2-A, T2-B, T3-A, T5-B,
  T6-B, T7-A. Even so they went into the journal as an attempt with an error and an empty patch, because the gateway
  only counts as a failure of the model path the provider's 403, 429 and 5xx responses, and this one came as 400.
- That is why repetition 1 looked complete and cheap (US$ 2.46) and the balance gate released repetition 2 at
  08:39:29. The script was stopped by hand at 08:40: 4 attempts of repetition 2 had opened a run on the gateway (US$ 0
  each, one refused call each) and **none went into the journal**. The `end` record of repetition 1 and the `start`
  record of repetition 2 in `results/budget-c1.jsonl` were written with that wrong cost.
- Spent on the gateway: US$ 3.1928 of US$ 15. The machine went back to 8 vCPUs at 08:44 while the collection waits.

No rule was changed. What to do with the 10 affected attempts and the gateway fix are a new amendment, to be written
with his decision before any new model call.

## Amendment of 16/11/2026, 10:35 UTC (written after the incident, with the machine stopped and before any new model call; applied at 10:41 UTC)

**How it was approved (literal record):** the proposal was explained to Francisco (which the 10 runs are, what failed,
why T7-B is redone too). He answered "Ah entendi..." ("Ah, I see..."), said he would put in about US$ 13 of credit
and, after receiving the request for the two confirmations (redo the 10; turn the machine on), answered **"Feito"**
("Done"). The agent read that as credit on the account and an ok to go on; the reading is the agent's, not words of
his. Since nothing was deleted, the decision can be undone: the 10 original lines are in `results/voided-c1.jsonl`.
**Explicit confirmation, afterwards:** told that the "Feito" had been read as an ok to redo the 10 and turn the machine
on, Francisco answered **"Sim ok pode seguir"** ("Yes ok, go ahead") (16/11, with the collection already resumed).

**Application, 10:38 to 10:42 UTC:** machine turned on at 32 vCPUs; gateway swapped for the new code with its state
intact (US$ 3.1928 and 282 requests before and after); `cases/void_tries.py` run: 6 lines in the journal, 10 in
`voided-c1.jsonl`, 14 infrastructure records, 2 balance records moved. Collection resumed at 10:42 UTC with ids `-t2`;
the first calls were accepted by the provider.

**Evidence from outside the pod for the 10, and a limit:** the gateway log of that hour was not kept (the container's
log was lost when the pod restarted; the facts of the incident above were read from it at the time). What stayed on
disk is the gateway's state per run: in the 10 runs, and only in them, the gateway counted **one call more** than the
agent received (1 against 0 in the eight that did not run, 15 against 14 in T4-B, 44 against 43 in T7-B), all closed
after 08:27:12; in the 6 valid ones the two numbers are equal. From now on the gateway log is written to
`~/logs/gateway-*.log`.


- **E20 · A refusal of the account by the provider is not an attempt.** The rule of 13/11 already said that an attempt
  that did not receive the model calls because of a failure outside the agent is not a result and is redone, as long
  as the gateway confirms it. What was missing was the gateway recognising this failure: it only counted the
  provider's 403, 429 and 5xx, and the lack of credit came as 400. The amendment closes that hole; it does not create a
  new success criterion.
  - **Gateway (`gateway/gateway.py`):** two provider responses are now read as a refusal of the gateway's own account,
    which the agent has no way of causing (only the gateway sends the key): **401**, and the **400 whose error message
    starts with "Your credit balance is too low"**. Each one is recorded in the run (`provider_auth`,
    `provider_billing`) **and stops the gateway**: no following call is forwarded. `POST /resume` on the admin port
    releases this kind of stop, and only this one, after the account is fixed. A 400 with any other message is still
    an error of the request itself (including one that merely quotes the sentence in the middle of the text).
  - **Runner (`cases/attempt_team.sh`):** (1) with the gateway stopped, the attempt does not even start: it does not
    open a run nor use up one of the 3 infrastructure attempts; (2) if the run's close brings `provider_billing` or
    `provider_auth`, the run **is not an attempt, whatever the agent reported and whatever the validator would say of
    the partial patch**; it goes to `results/infra-<round>.jsonl` and is redone with a new id (`-t2`). The gateway says
    so, not the pod.
  - **Application to the incident:** the 10 affected runs leave the journal and are redone: T4-B and T7-B (cut off in
    the middle) and T1-A, T1-B, T2-A, T2-B, T3-A, T5-B, T6-B, T7-A (never ran). **T7-B is redone even though it gave
    `resolved`**: the rule looks at the cause, not at the verdict, otherwise the result would choose what stays. The 6
    that finished before 08:27:12 stay as they are. The 4 openings of repetition 2 (`c1-t5-b-r2`, `c1-t7-b-r2`,
    `c1-t1-a-r2`, `c1-t2-a-r2`, US$ 0, never in the journal) get an infrastructure record so that the runner uses a new
    id.
  - **Nothing is deleted** (`cases/void_tries.py`): the 10 lines go to `results/voided-c1.jsonl`, the patches and
    verdicts to `results/patches/c1/voided/`, the previous journal is copied, and the two balance records written with
    the wrong cost (`end` of repetition 1, `start` of repetition 2) go to `results/budget-c1.voided.jsonl`. The `start`
    of repetition 1 stays: its cost still counts everything the gateway recorded since then, including the US$ 0.7182
    of the two runs that were cut off, as E19 requires.
  - **What the report and the video say:** that the account ran out of credit in the middle of repetition 1, how many
    runs were redone and why, and that their spending is in the total cost. The success rate uses only the journal.
  - **Limit:** a stop because of an account refusal is only released by a person (`POST /resume`); the first call
    after that is the test that the account is back, and if it is refused again the run becomes one more
    infrastructure record (at most 3 per attempt, then the runner asks for a person).
  - Tests: `gateway/test_budget.py` (check 22), `infra/test_attempt.py` (5 checks: the runner against the real gateway
    and a fake provider, and the migration on a copy of the round). `agent/` did not change (prompts and agent frozen
    at commit [the private commit that froze them]).

## Closed on 16/11/2026, 05:40 UTC (before any attempt of the experiment)

- **Validator controls, all 8 tasks:** owner's fix = `resolved` and empty patch = `not_resolved` in all of them
  (records in `tasks/records/T#-{gold,empty}.json`). The controls of tasks 2 and 3 that fell into the clock test (rule
  prior to E18) are kept as `T2-gold.before-E18.json` and `T3-gold.before-E18.json`. In the redone control of task 3
  the same case failed at 03:59 UTC and passed in both repetitions after 04:00 (unstable in that attempt).
  Limit: the new step of E18 (running the file with the owner's fix) was never exercised in the box, only in the local
  tests (`infra/test_team.py`, 21 tests), because the redone controls ran outside the window.
- **`order.csv`:** seed 20261115, 3 blocks of 16 attempts, generated from `tasks.csv` (sha256 `85c9aff30e26f9a7…`).
- **Prompts:** `agent/` at commit [the same private commit that froze the prompts and the agent] (the project notes
  list the same files the validator rejects).
- **Quote (outside the data):** task 1, single agent US$ 0.0899 and team US$ 0.1478; task 2, single agent US$ 0.1829
  (17 calls) and team US$ 0.3089 (36 calls); the four patches validated as `resolved` (the single agent's on task 2
  after being revalidated outside the clock window). Spent on the gateway: US$ 0.7295 of US$ 15.

## End of the collection, 16/11/2026, 12:42 UTC (record of facts; no rule changes)

- **Run:** 2 complete repetitions, 32 of 32 attempts in the journal (`results/attempts-c1.jsonl`, on the VM).
  Repetition 3 **did not run**: E19's gate read US$ 3.8865 of balance and required US$ 6.5671 (1.25 × US$ 5.2537). The
  script foresaw 3 repetitions; the video says "two runs each".
- **Repetition 1:** 07:58:45 to 11:24:32 UTC, with the incident's stop in the middle (08:27 to 10:42). Cost
  US$ 5.2537, which includes the US$ 0.7182 of the two runs cut off by the lack of credit. 10 runs redone (E20), all
  accepted by the provider. **Repetition 2:** 11:24:32 to 12:42:11 UTC, released with US$ 9.0168 of balance against
  US$ 6.5671 required; cost US$ 5.1303. After the resumption no call was refused and no new infrastructure record was
  written (the 14 in `infra-c1.jsonl` are from the incident).
- **Gateway at the end:** US$ 11.1135 of US$ 15 (quote US$ 0.7295 + cut-off runs US$ 0.7182 + 32 attempts
  US$ 9.6656); 943 requests, 18,125,255 input tokens and 420,451 output tokens.
- **Required checks (validator, E10 + E18), per setup and repetition:**

  | | repetition 1 | repetition 2 | total | spent |
  |---|---|---|---|---|
  | A · single agent | 6 of 8 | 7 of 8 | 13 of 16 | US$ 3.9945 |
  | B · team | 7 of 8 | 7 of 8 | 14 of 16 | US$ 5.6711 |

  This is "passed the checks", not "fix": the blind judging is still missing (below).
- **The 5 that did not pass** (all decided in stage 1, F2P cases still failing):
  - T3-A, repetition 1: the agent stopped by response size (4,096 output tokens) with US$ 0.1860 spent and an **empty
    patch** (861 of 861 F2P failing);
  - T8-A, repetition 1: stopped by the per-attempt limit with US$ 0.4244 spent (182 of 204);
  - T8-B, repetition 1: stopped by response size with US$ 0.3115 (203 of 204);
  - T8-A, repetition 2: stopped by the per-attempt limit with US$ 0.4254 (185 of 204);
  - T8-B, repetition 2: stopped by the per-attempt limit with US$ 0.4530 (185 of 204).
  Task 8 (the one that crosses the three areas) did not pass in any of the 4 attempts, and in none of them did the
  agent get to the end: what the 4 measure is the US$ 0.75 limit and the 4,096-token limit, not each setup's ability on
  that task.
- **Limit reached and still passed:** T7-B, repetition 1 (US$ 0.5857 spent).
- No `infra_error` or `timeout` verdict (nothing to redo under E16); no broken, unstable-in-the-attempt or
  environment-dependent case in the 32 validations; no attempt reached 40 min or 150 tool calls.
- **Machine:** back to 8 vCPUs at 12:46 UTC (ledger 8 / 26, `/dev/shm` 28G); the gateway came up with its state intact.
  Copies on the VM: `~/backup/c1-complete-20261116T1243Z.tgz`, `gw-state-after-c1-20261116T1243Z.json` and the gateway
  log since the resumption (`~/backup/gateway-logs/gateway-full-20261116T1243Z.log`, 717 lines).

## Amendment of 16/11/2026, 12:49 UTC (written after seeing the validator's verdicts and BEFORE any person or agent read a patch; the packets were generated at 12:51 UTC)

- **E21 · Blind judging: what becomes a packet and how it is shown.** The script already fixes the rule (Francisco
  judges without knowing whether the patch is from A or from B, with his diff next to it; equivalent / valid / worse /
  inconclusive, with V5's definitions). This amendment only closes the mechanics, the same for both setups:
  - **Packets:** one per `resolved` attempt (27). The 5 `not_resolved` are not a fix under E10 and are not judged.
  - **What the packet shows:** the task (number, areas and the task statement the agent received), the commit's test
    files, the validator's summary, the agent's patch and the code of his commit (`fix-source.diff`, without the tests,
    which were already in the box), with the count of files and lines of each.
  - **What the packet does not show:** setup, repetition, run id, cost, number of calls, time, and the final text of
    the agent and of the review (the text may mention subagents). The packet id is random, all files have the same
    date, and the key (`results/blind/key.jsonl`, on the VM) is only opened after all 27 have a verdict.
  - **Counts as a fix:** `resolved` **and** a verdict of equivalent or valid. Worse and inconclusive do not count; each
    inconclusive is stated in the video.
  - **Where it runs:** the page (`judge/`) runs on the VM, only on 127.0.0.1 (port 8796), and he opens it through an SSH
    tunnel; patches, verdicts and key do not leave the VM. What comes back to the repository is counts.
  - **Limits:** (1) he has already seen, per setup and task, who passed the checks (progress report of 16/11); the
    packets do not say whose each patch is, but on task 3 he knows there is 1 patch from A and 2 from B. (2) The agent
    that assembled the packets saw the size in bytes of each patch next to the run id, not the content. (3) A patch can
    give away the setup through its style; there is no control for that.

## Record corrections, 16/11/2026, 13:24 UTC (after two external reviews pasted by Francisco; no verdict or number changes; no patch was read)

Each point was checked in the code and in the VM's records before entering here.

- **The 4,096 output-token limit is the agent's, not the gateway's.** The record of 08:25 UTC and the end of the
  collection say "a gateway limit": wrong. It is `MAX_TOKENS` in `agent/agent.py` (the same for A and B); the gateway
  accepts up to 8,192 per call. This limit **is not in the protocol's list of limits** and caused the only difference
  in the "passed" count: the single agent on task 3, repetition 1, stopped at it before writing any file. It joins the
  limits stated in the video.
- **The review stage is not identical; the reviewer's prompt is.** In A, the agent always does one review and one
  correction turn in the same session (which has already seen the test commands). In B, the reviewer is a subagent
  called when the orchestrator decides (or by the harness, if the orchestrator does not call it), and it receives the
  task statement and a summary of the diff. The script says "the same review stage"; the line becomes "the same
  reviewer instructions".
- **Task 8: the count of failing cases does not measure progress.** In the 4 attempts, 5 of the commit's test files do
  not load in any sample, the same number as in the control with an empty patch; most of the "182 to 203 of 204" comes
  from that.
- **Report counts:** the team's `tool_calls` includes 41 dispatch and review calls; `tool_errors` counts every non-zero
  exit (a `grep` with no result included). "Largest call of the round" holds only for the 26 attempts with a log.
- **`report/c1-attempts.csv` carried the patch size next to the setup** (commit [the private commit that added that
  column]), which would allow linking packet and setup. The column was removed; the git history still has it.
  Francisco does not open that file or that commit before judging. The script that generates the report is now in the
  repository (`cases/summary_team.py`, `cases/context_per_run.py`); before it was a loose script.
- **Holes that did not trigger in this round, to close before V7 reuses the harness:** (1) the path validator accepts
  a new file that the test runners load by themselves (`flutter_test_config.dart`, `__mocks__/`); (2) if the agent
  does `git commit`, the patch comes out empty (the harness takes `git diff` against HEAD). The third item of the
  review came cut off in the paste.
- **Open finding, with a proposal pending his decision (E22, below once approved):** the validator counts a case as
  passed if the case says `pass`, even if its file ended with an error (timeout after the assertions, or a failure in
  `afterAll`), and the case-by-case results of each sample were deleted after being read (only the counts stayed).
  Reproduced with synthetic data. What the records show of the 27 that passed: none has a file error in stage 1; 7
  have a file error in stage 2 (the 4 of task 2 and the 3 of task 3), with the **same counts per job as the control
  with the owner's fix** (task 2: 1 and 1; task 3: 2). The file names were not kept, so the equality is of counts, not
  of files; and a red Jest file with no failing case does not appear in any count.

## Amendment of 16/11/2026, 13:32 UTC (new rule, created AFTER seeing the validator's verdicts and before any judging; written before running the revalidation)

**Origin and approval (literal record):** two external reviews pasted by Francisco found that the validator passed a
case in a file that ended with an error and that the case-by-case results were not kept. The agent asked "Posso
revalidar em 32 vCPUs?" ("Can I revalidate on 32 vCPUs?"); his answer was two more pasted reviews, with no text of his
own, both saying to revalidate before judging, on 32 vCPUs, after fixing two defects of the first fix. The agent read
the paste as his request; the reading is the agent's.

- **E22 · A file that did not finish clean does not pass a case; every result is kept; the saved patches are
  validated again.**
  - **Rule (the same for A, B and controls):** a required case (F2P or P2P) only counts as passed in a sample if the
    case says `pass` **and** its test file finished clean in that sample. Dirty file = executor file error (did not
    load, `setUpAll`/`tearDownAll` failed, did not run), file process ended by timeout (code 124), or red Jest file
    with no failing case (for example, `afterAll` threw). The same reading holds for the tree with the owner's fix in
    E18's control: a file that is also dirty with the owner's fix, at the same hour, is *environment-dependent* and
    does not count against the patch. The lists in `tasks.csv` and `cases.json` do not change.
  - **Evidence:** the complete result of each sample is kept in `/srv/ci/keep/<pod>.json.gz`. If it cannot be written,
    the sample is not a result (the validation ends as `infra_error`) and the original is not deleted.
  - **Also closed:** a sample whose record the validator cannot read becomes `infra_error`, and the validation refuses
    to start if there is a required case listed under a job that is not among the task's jobs.
  - **First version wrong, fixed before running:** commit [the private commit with that first version] read the field
    `files` (list of the patch's files) instead of `file_times` (state of each test file) and did not stop when writing
    failed. The review found both; the tests passed because they simulated the wrong format. Now there is a test that
    builds the record with the executor's own Jest collector and checks the format in its code.
  - **Application to round c1, with no model call (`cases/revalidate_team.sh`):**
    1. a small integrated test first (the two controls of task 1, in the box);
    2. the 16 controls (owner's fix and empty patch of the 8 tasks). **If any control with the owner's fix does not
       give `resolved`, or any with an empty patch does not give `not_resolved` on F2P, it stops there:** the 32
       patches are not touched and the divergence is investigated and shown to Francisco;
    3. the 32 saved patches, 4 at a time, on the machine at 32 vCPUs (same per-pod limits as the collection).
  - **Nothing is overwritten:** the collection's verdicts stay in the journal and in `results/patches/c1/`; the new
    ones go to `results/revalidate-c1/` and the new controls to `/srv/ci/validate/E22/`. The report and the video say
    both numbers ("27 before, N after").
  - **Which verdict holds:** the new one. A patch that drops from `resolved` to another result stops being a fix and its
    packet leaves the page; the packets that stay **keep the same id** and the key stays closed. A new `infra_error` or
    `timeout` follows E16 (redone once). A `not_resolved` patch that gave `resolved` now would be a sign of an error
    (the rule only got stricter): it is investigated, not accepted.
  - **Limits:** the rule was created after seeing who passed; it only gets stricter, applies equally to both setups and
    was written without reading any patch. The revalidation runs at a different hour from the collection (cases that
    depend on the clock fall into E18's control). The case-by-case results of the original collection are still lost:
    what becomes auditable is the revalidation.
- **Third hole on the list for V7** (came in the following review): nothing checked that all the test jobs on the list
  ran. The refusal above covers the case of a job with required cases outside the list of jobs; checking that each job
  on the list produced a sample was already done (a missing sample ends the validation without a verdict).

**Application of E22, 16/11 (record; times in UTC from the VM's clock and the commits):** the titles of the two sections
above came out with the wrong time in the first writing (14:00 and 14:40) and were corrected to the time of the commits
(13:24 and 13:32). Code sent to the VM at 13:36 (the two previous files kept in `~/backup/*.before-e22`); the 26 tests
pass there.
**Integrated test, 13:36 to 13:41, machine at 8 vCPUs:** the two controls of task 1 with the new rule: owner's fix
`resolved` (stage 2, 4 samples), empty patch `not_resolved` (3 of 3 F2P failing). The 7 results stayed in
`/srv/ci/keep/`, and the executor's real record has `file_times` as a dictionary and `files` as a list, as the contract
test asserts. Machine at 32 vCPUs at 13:44 (ledger 32 / 104, `/dev/shm` 112G); revalidation started at 13:44:53
(`~/logs/start-revalidate-c1.sh`, log in `~/logs/revalidate-c1.log`). The judging page stays offline until it
finishes; no verdict had been given.

**Result of the revalidation (E22), 16/11, 13:44:53 to 16:05:27 UTC, 32 vCPUs:**
- **Controls (16):** the 8 owner's fixes `resolved` and the 8 empty patches `not_resolved` on F2P, with the new rule.
- **Patches (32): 31 with the same verdict as in the collection, 1 changed.** In the 26 that are still `resolved`, no
  dirty file had a required case (the dirty files of tasks 2 and 3 are the same as in the control with the owner's fix
  and have no case from the lists). No broken, unstable or environment-dependent case.
- **What changed: T1-A, repetition 2 (`c1-t1-a-r2-t2`), from `resolved` to `not_resolved` (stage 1).** The commit's
  test file (the rules one) ran 3 times with the patch: in samples 1 and 3 the 1,116 cases passed, file clean, in
  232.6 s and 230.9 s; in sample 2 the process was ended by the 300 s per-file limit (code 124, 300.4 s) **without
  reporting any case**. The rule prior to E22 would give the same result (missing case = did not pass): the change does
  not come from the new rule, it comes from the termination.
- **Time of that file:** 120 to 176 s in the controls with the machine unloaded; 194 to 278 s in the patches' samples,
  with 4 validations at the same time. The only other termination at 300 s was in `c1-t8-a-r1` (sample 1), which is
  `not_resolved` because of the other samples anyway. The 300 s per-file limit is the executor's default
  (`file_timeout`), not a protocol rule.
- **Pending Francisco's decision:** follow the rule as it is (that patch's packet leaves; 26 passed: A 12 of 16, B 14
  of 16) or treat "file ended by the limit before reporting any case" as a sample that is not a result, redone once
  with the same limits (for everyone; today only those two cases). The judging page stays offline until the decision.
- **Kept:** `~/backup/revalidate-c1-20261116T1606Z.tgz` on the VM (new verdicts, new controls, the 240 complete sample
  results, log). Machine back to 8 vCPUs at 16:08 UTC; gateway intact (US$ 11.1135).

## Amendment of 16/11/2026, 16:14:48 UTC (new rule, decided AFTER seeing the result of the revalidation; written before running, which started at 16:14:56)

**Approval (literal record):** the agent showed the two options for patch `c1-t1-a-r2-t2` (follow the rule as it was,
or treat the termination by the limit as a sample that is not a result and redo it once), recommending option 2.
Francisco answered **"Pode ser a 2"** ("Option 2 is fine").

- **E23 · A file ended by the limit before reporting any case is not a verdict.** A test file that has a required case
  and was ended by the per-file limit (code 124) **without reporting any case** says nothing about the patch. The
  sample is not a result: the validation ends as `timeout`, and E16 already requires redoing it **once** on the same
  saved patch, with the same limits; a second `timeout` counts as not a fix (a patch can hang the tests). A file ended
  with no required case changes nothing. A file ended **after** reporting cases is still dirty under E22. Applies to A,
  B and controls (`cases/validate.py`, new test in `infra/test_team.py`, 27 pass).
- **Application to the revalidation of c1:** only two samples of the 240 had a termination by the limit, both in the
  rules file: `c1-t1-a-r2-t2` (sample 2 of stage 1) and `c1-t8-a-r1` (sample 1 of stage 1). Under E23 the two
  validations become `timeout` and are redone once each, one after the other, with the machine at 8 vCPUs and nothing
  else running. The result of the new validation holds. The files of the first revalidation stay; the new ones go to
  `results/revalidate-c1/<run>.e23.verdict.json`. No control had a termination.
- **Limits:** the rule was created after seeing the result and, in this round, can only change one verdict, of one
  setup (A); the video says so. The 300 s per-file limit does not change.

**Result of E23, 16/11, 16:14:56 to 16:29:34 UTC (8 vCPUs, nothing else running):**
- `c1-t1-a-r2-t2`: **`resolved`** (stage 2). The rules file ran in 177.3 s, 175.4 s and 174.9 s, all cases passed,
  file clean; the area's suite passed.
- `c1-t8-a-r1`: `not_resolved` (stage 1), as before: 180 F2P cases failing in Flutter in each sample; the rules file
  this time finished in 130 to 183 s.
- **Final verdicts of round c1 after E22 and E23: the same as in the collection.** A 13 of 16, B 14 of 16; 27 packets in
  the blind judging, the same ones, with the same ids. The video says that the validator was made stricter after the
  collection, that everything was validated again and that no verdict changed, and that one patch only kept its
  verdict because the termination by the limit was treated as "not a result" by a rule created after seeing that case
  (E23).
- **The two repetitions of E23 ran with less concurrency than the revalidation:** one validation at a time on 8 vCPUs,
  against 4 validations at the same time on 32 vCPUs in the revalidation (and in the collection). The rules file took
  175 to 177 s in them and 194 to 300 s in the revalidation. The machine's condition changed between the first attempt
  and the repetition; this goes with the final numbers. (Title of this amendment corrected from "16:20" to the time of
  the commit, 16:14:48 UTC, after an external review.)

## Record of 16/11/2026 · judging delegated to Codex, after E23

**Francisco's literal authorization:** "pode julgar la pra mim please" ("go ahead and judge them there for me,
please"). The judge of this round becomes **Codex by delegation of the user**. This does not constitute independent
human judging. The authorization was recorded on the VM before the votes; this record consolidates the result after
the check of what was recorded.

- The 27 eligible packets were reviewed, comparing task statement, patch, reference commit and relevant excerpts of
  the original tree. The four categories and the definition of a fix from E21 were kept.
- **Result: 7 equivalent, 9 valid, 11 worse, 0 inconclusive and 0 pending.** Therefore, 16 of the 27 patches that
  passed the required checks also count as a fix in this judging.
- Each vote has its own justification, the patch's hash, `source=codex_delegated`, `reviewer=Codex` and
  `user_delegated=true`. The later read of the API and of the CSV confirmed all 27 records and their justifications.
- **Method and limit:** static code review supported by the revalidation already finished (E22/E23). The counter-cases
  in the justifications are derived from the code; no new reproductions on a device and no new rounds of the
  experiment were run for this judging.
- The key that links the packets to the setups remains closed. No per-setup result was computed at this stage. Patches
  and detailed justifications remain on the VM; only these counts come back to the repository.
- Evidence on the VM: `~/lab/results/blind/codex-review-2026-11-16/` [the lab user's home directory, shortened for the public copy] contains `delegation.json`,
  `review.json` and `verification.json`; official votes in `results/blind/verdicts.jsonl` and `verdicts.csv`.
  The script and the report must attribute this assessment to Codex, without describing it as a review done by
  Francisco.

## Blind judging, 16/11/2026 (record written BEFORE opening the key)

- **Who judged:** **Codex**, by delegation of Francisco ("pode julgar la pra mim please" ("go ahead and judge them
  there for me, please"), recorded in `results/blind/codex-review-2026-11-16/review.json` on the VM). To the agent
  (Claude) he wrote: **"Feito pelo Codex, aprovado por mim. Pode continuar."** ("Done by Codex, approved by me. You can
  carry on."). E21 and the script said that Francisco would judge; the judging is Codex's, with his approval. The video
  says so ("judged blind by another model, Codex, and approved by me"), not "my own blind judgment".
- **How:** static review of the task statements, the patches, the reference commit and the base code the patches
  touch; without running anything beyond the required validation that already existed. The verdicts were recorded
  through the page's API (27 lines in `verdicts.jsonl`, all at 17:22:34 UTC, origin `codex_delegated`, each with a
  note), not by clicking.
- **Blind result:** 27 of 27 judged: **equivalent 7, valid 9, worse 11, inconclusive 0.**
- **The key was not opened during the judging:** Codex's `verification.json` says `identity_key_opened: false`, and the
  last recorded access to `key.jsonl` on the VM is 12:51:05 UTC, the time it was written. Limit: the agent has no way
  of knowing whether Codex saw commit [the private commit mentioned in the record corrections of 13:24 UTC] (patch size
  next to the setup) in the local repository.
- Counts as a fix (E21): `resolved` **and** equivalent or valid. The key is opened now.
- **Key opened at about 17:29 UTC, after the record above.** Fixes (resolved + equivalent/valid): **A 7 of 16, B 9
  of 16**; spent per fix A US$ 0.571, B US$ 0.630. Detail in `report/c1-summary.md` and `report/c1-blind.csv`.

## Machine stopped, 16/11/2026 19:33:15 UTC (Francisco's ok: "Pode" ("Go ahead"))

- **Before stopping:** the collection logs that serve the scenes were copied to the SSD, in [the video's capture
  folder, on the author's external disk] (outside git), **with metadata only**: driver logs (collection, revalidation,
  E23), gateway log per call (10:41 to 12:31 UTC; the one from before that time was lost in the pod restarts, only the
  totals per run remain, in `gateway-budget.json`, without the token's hash) and the attempts with numeric fields and
  outcomes. Left out: the final text, the review text, the commands, the validator's file names and the patches. The
  search for paths and code extensions in the copied files found nothing.
- **Stopped, not deleted:** `aip-ci-01` in TERMINATED at 19:33:15 UTC; the 200 GB disk keeps billing. Patches, blind
  packets, judging notes, key and the Secret with the API key remain on the disk. Delete only with his ok.
- **Periods for the machine cost:** n2-standard-8 from 16:08 to 19:33 UTC joins the previous list of periods.

## Francisco's review of the notes of tasks 4 and 5, 16/11/2026 (after opening the key; no verdict changes)

An external review pasted by him asked him to read the notes of the two tasks that account for 8 of the 11 worse
before locking the script, because the video says "approved by me". The VM stayed stopped ("nao precisa ligar" ("no
need to turn it on")): the notes came from the agent's session history, and the reference side of each note was
checked in his commits, read-only. The patches' side is still only Codex's static reading.

- **Task 5 (bottom sheet margins on Android), 4 worse.** One patch (single agent, rep. 1) keeps the fixed minimum that
  the task said to remove (with a 16 px bar it gives 40 instead of 32). The other three ignore, on Android, the
  helper's padding parameter; Codex's counter-example (24 + 32 → 40, reference 56) matches the commit, but at the time
  no screen passed padding above 16, so no screen of the app changed. Question put to him: a silently ignored
  parameter, with no screen affected, is it worse or valid? **Answer: "pior" ("worse").**
- **Task 4 (chat between host and participant), 4 worse.** His commit makes the conversation read-only for whoever
  opens it, host or participant, when the participant cancels or is removed, and checks again after the delete-message
  dialog. Three patches (single agent rep. 1, team rep. 1 and 2) only lock the participant's screen; one (single agent
  rep. 2) locks both sides but deletes the message if the registration ends with the dialog open. Questions: should the
  host's screen also be read-only? **"sim" ("yes")**. Is deleting in that window worse or acceptable? **"pior"
  ("worse")**.
- **Result:** the 8 verdicts stay as Codex gave them; fixes A 7, B 9; 11 of 27 worse. The other 3 worse (task 2, two;
  task 7, one) were not reviewed by him.
- **Script:** the example of scene 08 stops being the padding one (it suggested a visible defect that no screen had)
  and becomes task 4's; the line says that the judging read the code without running it and that he checked those
  decisions.

## VM deleted, 16/11/2026 21:55:41 UTC (Francisco's ok: "pod3 copiar sim, ai depois apaga" ("yes, you can copy it, then delete it"))

- **Before deleting:** the VM was turned on at 21:42 UTC only to copy the audit record to the SSD ([an archive on the
  author's external disk], `aip-ci-01-v06-team-20261116.tgz`, 14 MB, outside git): journal of the attempts with the
  model's text, the 32 patches, the 27 blind packets, verdicts with Codex's notes, the key, Codex's record, E22/E23
  revalidation, validation samples, logs and the gateway's state. Left out: the app's snapshots and the dependency
  caches (reproducible from the app's repository) and all secrets; the script refused to build the archive if it found
  a key. Checksums of the journal, the verdicts, the key and the CSV equal to those on the VM.
- **Deleted:** the instance `aip-ci-01` and the disk (`--delete-disks=all`, explicit project, labels checked). No
  resource with the `aip-` prefix left in the project.
- **Machine cost:** US$ 16.87 at list price (row `A-v07-gcp-vm` of [the cost ledger in the private production
  repository]); the video says "about seventeen dollars".
- The Anthropic API key used by the gateway is gone from the VM along with it, but it is still valid on his account; he
  revokes it when closing the experiments (V7 will need one).
