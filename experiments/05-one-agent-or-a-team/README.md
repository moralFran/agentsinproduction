# Experiment 05 · One coding agent or a team, on 8 real changes to a production app

> Video: "One agent or a team? I re-ran 8 real tasks from my app both ways"
> TODO: add the video link here once it is public.

**The question.** The usual advice for coding agents is to split the work into a team: a planner, a few specialists,
a reviewer. Does that pay off on real code? I took 8 changes I really made in a production app and ran each one under
two setups, one agent and a team, two runs each, with the same model and the same limits. Results:
[`results.md`](results.md). Rules written before the runs, and every later amendment with its date:
[`criteria.md`](criteria.md).

Names: this is **experiment 05** of the channel and the sixth video (production id `A-v07`, private folder `v06-team`).
The GCP label `experiment=aip-v06-team`, the VM name `aip-ci-01` and the run ids (`c1-t4-b-r2`: round c1, task 4,
setup B, repetition 2) come from the production numbering and were kept, because the recorded results refer to them.

## What is and is not in this folder
The app is private, so **its code is not here and these exact tasks cannot be re-run from this folder.** Left out on
purpose: the app's snapshots, the task texts and test lists (`tasks/`), the agents' patches and transcripts, the blind
packets and the judge's notes (they quote the app's code). They stay in a private archive.

Here: the whole harness (agent, team orchestration, gateway, validator, Kubernetes manifests, VM scripts), the prompts
as they were run, the rules and their amendments, per-attempt numbers, the collection logs with metadata only, and the
scripts that print the terminal tables shown in the video.

Edits for the public copy, all marked where they are:
- The Firebase emulator project ids are replaced: `app-test`, `app-rules-test` and `demo-app-e2e-fn` (in
  `agent/areas.txt`, `cases/prep_team.py`, `executor/team.py`, `infra/test_team.py`).
- Names of the app's own test files and of one test case are replaced (`cases/team_host.py`, `cases/report_team.py`,
  `executor/team.py`, `infra/test_team.py`): the one timing test the harness leaves out by name is now
  `test/redacted_timing_test.dart::Timing group timing case (name redacted)`. The local tests still pass. Nothing else
  in the code changed.
- `criteria.md`, `report/c1-summary.md`, `infra/TEARDOWN.md` and `infra/locks/README.md` are translated from the
  Portuguese originals, with the redactions listed at the top of each. `infra/TEARDOWN.md` was carried over from
  experiment 04 and not updated; a note at its top says what is stale.
- `capture/collect_replay.py`: one line of its docstring now says where the log is in this folder.
- `agent/agent.py`: its docstring said the setups differ "only" in how the context is split; corrected on 17/11 after
  an external review (the review also runs differently). Docstring only, marked in place.
- `executor/team.py` (17/11, after an external review, **a behaviour change for future runs**, not what the recorded
  collection ran): a `flutter test` process that exits non-zero although it reported no failed case now marks its files
  dirty. Test added in `infra/test_team.py`. See [`results.md`](results.md#limits). On 23/11, after a third external
  review, also when the process is killed (rc 124 or a signal) after reporting a failed case; test added. Neither case
  happened in this collection.

## Setup
One ephemeral GCP VM (`n2-standard-8`, resized to `n2-standard-32` for the collection so 4 attempts could run at
once; nested virtualization, **no service account**), with k3s and Kata Containers, as in
[experiment 04](../04-ci-failures). Every agent and every test run is its own Kata pod (own guest kernel), uid 1000,
no service-account token.

| Role | Where | What it can reach |
|---|---|---|
| **Agent** (setup A or B) | pod in `ci-agent` | only the gateway's model port (NetworkPolicy; before the agent starts, an init container checks that forbidden destinations do not connect over several consecutive rounds, which shows the rules were in force then, not for the whole attempt); no credentials, no internet, no DNS. Gets a snapshot of the app as it was just before my commit, with my commit's tests put back and **no history** (one commit, no remotes), the task text and the output of the failing tests. **Never my fix.** |
| **Gateway** | pod in `ci-gateway` | holds the provider key; forwards only `POST /v1/messages`; a budget per attempt (US$ 0.75) shared by every agent of that attempt, plus a total budget (US$ 15); logs every call. Before each call it reserves the worst case of that call and refuses it if the attempt's budget cannot cover it. |
| **Validator** | pods in `ci-exec` | no network allowed (NetworkPolicy; the same init-container check before the tests start, so by sampling, not continuous). Applies the patch and runs, in order: path rules (no test, CI, configuration or lock-file change); my commit's test files, 3 samples, every case must pass; one sample of each touched area's suite, which must keep passing (a file that fails is rerun twice; failing again = broken). |
| **Blind judging** | packets built on the VM (`cases/blind_team.py`) | each patch the validator called `resolved` becomes a packet with a random id: the task as the agent got it, my commit's test files, the validator's summary, the agent's patch and my commit's code. It never shows the setup, the repetition, cost, calls, time or the agents' final text. The key stays closed until every packet has a verdict. |

**Setup A, one agent** (`agent/single.txt`): one session reads, plans, implements and runs the tests. When it says it is
done, the harness sends the review instructions (`agent/reviewer.txt`) into the same session, then asks it to fix what
its review found.

**Setup B, a team** (`agent/orchestrator.txt`, `agent/subagent.txt`): an orchestrator plans and dispatches one
subagent per area (security rules, back end functions, Flutter app), then calls a reviewer subagent with the same
review instructions as A. Every subagent starts from its own context: the shared project notes, its role prompt and
the task the orchestrator wrote for it. Subagents run one after another, not in parallel.

Same for both (`agent/agent.py`): model `claude-sonnet-5-5`, one `bash` tool, the shared project notes
(`agent/project.txt`, `agent/areas.txt`), and the same limits **for the whole attempt**, summed over every agent of the
team: 40 minutes, 150 tool calls, US$ 0.75 of model calls, and 4,096 output tokens per reply. So the two setups differ
in how the work is split and in how the review runs, not in model, tools or limits.

## Method
Rules closed on 15/11/2026 (day/month), before any run; amendments dated in [`criteria.md`](criteria.md).
- **Tasks:** 8 commits of mine in the app (`tasks.csv`), each with tests that fail before it and pass after it. A task's
  "fail to pass" cases are the cases of my commit's test files that fail 3/3 on the snapshot and pass 3/3 with my fix;
  the area suites give the "pass to pass" cases. Controls before the collection: my fix must come out `resolved` and
  an empty patch `not_resolved`, for all 8 (16 of 16 did).
- **Order:** shuffled, seed 20261115 (`order.csv`); 3 repetitions planned.
- **Budget:** at most US$ 15 of model calls for the whole experiment, quote included. Repetition 1 starts only if 16
  attempts at the US$ 0.75 cap fit in what is left; each later repetition only if what is left is at least 1.25 × the
  cost of the most expensive complete repetition (`cases/budget_gate.py`). Repetition 3 needed US$ 6.57 and US$ 3.89
  were left, so it did not start (`report/collection/budget-c1.jsonl`).
- **One outcome per attempt.** Did the patch pass the validator (`resolved`)? If yes, a blind verdict against my commit:
  **equivalent** (same cause fixed, same observable behaviour), **valid** (different code, does what the task asks,
  nothing on the "worse" list), **worse** (passes the tests but misses part of the task, breaks something that worked,
  or changes behaviour the task did not ask for). **A fix = `resolved` and equivalent or valid.**
- **Judging:** done blind by another model (Codex), by my delegation, with the key closed; approved by me. After the key
  was opened I checked the judge's notes on tasks 4 and 5, which hold 8 of the 11 "worse"; all 8 verdicts stayed. The
  judge read the code; it did not run the patches.
- **Amendments after seeing data**, all in `criteria.md` and in [`results.md`](results.md#limits): the provider account
  ran out of credit during repetition 1 and the 10 attempts it cut were voided and re-run (E20); the validator was made
  stricter after the collection and every attempt re-checked (E22); and one rule (E23) was written after seeing the
  attempt it affects.

## Reading the numbers
Everything in `results.md` comes from `report/` and `report/collection/`:
```
cd report
python3 ../capture/show_results.py grid    # per task and repetition: fix / worse / failed
python3 ../capture/show_results.py tally   # passing patches and verdicts per setup
python3 ../capture/show_results.py cost    # spend, calls, cache share, cost parts, per fix
cp collection/gateway-20261116T1041Z.log gateway.log && source ../capture/gw.sh && gw c1-t8-a-r2   # one run in the gateway log
python3 ../capture/collect_replay.py collection/collect-c1.log 2 0                                   # the collection log, repetition 2
```
These are the scripts that printed the terminal tables in the video.

| File | What it is |
|---|---|
| `report/c1-attempts.csv` | one row per attempt: outcome, validator verdict, cost, model and tool calls, tokens, time, team roles |
| `report/c1-blind.csv` | one row per attempt with the blind verdict (`equivalente`, `valida`, `pior` = equivalent, valid, worse) and `fix` |
| `report/c1-context-per-run.csv` | input size per call, per attempt (26 of 32: the gateway log of the first hour was lost in pod restarts) |
| `report/c1-summary.md` | the run's summary tables, before and after the blind judging |
| `report/collection/attempts-c1.meta.jsonl` | the 32 counted attempts, numeric fields and outcomes only |
| `report/collection/voided-c1.meta.jsonl`, `infra-c1.meta.jsonl` | the attempts voided by the credit incident, and the infrastructure retries |
| `report/collection/collect-c1.log`, `revalidate-c1.log`, `e23-c1.log` | the driver's logs of the collection, the re-check (E22) and the E23 redo |
| `report/collection/gateway-20261116T1041Z.log`, `gateway-budget.json` | the gateway's per-call log from 10:41 UTC, and its totals per run |
| `report/collection/budget-c1.jsonl` | the budget check before each repetition |
| `tasks.csv`, `order.csv` | the 8 tasks (commit, snapshot, areas, case counts) and the shuffled order |

## Running the harness
It needs a private app with the same shape (Flutter client, Firebase back end, Jest tests run against the emulators)
and its own `tasks/` folder; the VM scripts are in `infra/` (create, setup, build images, teardown in
[`infra/TEARDOWN.md`](infra/TEARDOWN.md)). The scripts read the GCP project from `AIP_PROJECT` and never use the gcloud
default; the provider key goes from standard input straight into a cluster Secret. Local tests:
`python3 agent/test_agent.py`, `python3 executor/test_executor.py`, `python3 gateway/test_budget.py`,
`python3 -I infra/test_team.py`, `python3 infra/test_attempt.py` (19, 76, 25, 28 and 5 checks, all passing on the
public copy).
