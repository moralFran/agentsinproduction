# Experiment 06 · Long agent sessions: compaction, and what silently breaks the prompt cache

> Video: "97% of my agent's input came from cache. Here's what silently breaks it"
> TODO: add the video link here once it is public.

**The question.** In my own Claude Code sessions on my app, almost 97% of the input came from the prompt cache, and the
sessions compacted 19 times. So, on one long, real task: does compacting make the agent forget the task? Is a high
cache hit rate a small bill? And what breaks the cache without telling you? Results: [`results.md`](results.md). Rules
written before the runs, and every later amendment with its date: [`criteria.md`](criteria.md).

Names: this is **experiment 06** of the channel and the seventh video (production id `A-v08`, private folder
`v07-cache`). The GCP label `experiment=aip-ctx`, the VM name `aip-ctx-01` and the run ids (`v1-t8-l2-r1`: round v1,
task 8, condition L2, repetition 1; `rep-R4-…`: a replay of condition R4) come from the production numbering and were
kept, because the recorded results refer to them.

## What is and is not in this folder
The app is private, so **its code is not here and this task cannot be re-run from this folder.** Left out on purpose:
the app's snapshot, the task text and test lists (`tasks/`), the agent's patches and transcripts, the request bodies the
gateway logged (the replays were built from them; they hold the app's code), the review packets, and the reviewer's
notes and evidence. They stay in a private archive. The numbers from my own Claude Code sessions quoted in the video
are not data of this experiment and are not here.

Here: the whole harness (the agent with its phase and compaction logic, the gateway, the validator of experiment 05,
the Kubernetes manifests, the VM scripts), the prompts as they were run, the replay script, the rules and their
amendments, the numbers per model call, per attempt and per replayed request, and the script that prints the terminal
tables shown in the video.

Edits for the public copy, all marked where they are:
- Files this experiment took unchanged from experiment 05 are copied from [experiment 05's public folder](../05-one-agent-or-a-team),
  with the same redactions (Firebase emulator project ids replaced; names of the app's own test files and of one test
  case replaced). Files that changed here (mostly the VM name and the conditions) got the same change on top of that
  public copy.
- `infra/TEARDOWN.md`: experiment 05's translated copy with this VM's name and label; the note at its top says what is
  stale.
- `infra/test_attempt.py` (24/11/2026, test only, made in the private copy too): checks 1–4 call `attempt_team.sh` with
  the conditions L0 / L2 instead of experiment 05's setups A / B, and check 5 writes experiment 05's repetition-1
  order itself instead of reading this folder's `order.csv` (which has conditions, not tasks).
- `agent/agent.py`: a docstring note (24/11, docstring only) that the project guide was not in the system prompt (E7).
- `capture/show_results.py`: one line of its docstring now says where to run it.
- `lab.env` (the VM's internal address) is left out.

## Setup
One ephemeral GCP VM (`n2-standard-8`, nested virtualization, **no service account**) with k3s and Kata Containers, as
in experiments 04 and 05. The agent runs in its own Kata pod with no credentials and one network destination, the
gateway's model port; the validator's test runs are pods with no network.

**The agent** (`agent/agent.py`): configuration A of experiment 05, one agent in one session: it reads, plans,
implements and runs the tests; when it says it is done the harness sends the review instructions into the same session,
then one message asking it to fix what its review found. Model `claude-sonnet-5-5` with its default thinking and effort,
one `bash` tool plus `end_phase(summary)`, and limits per attempt: 40 minutes, 150 tool calls, US$ 4 of model calls
(raised from US$ 2 after the smoke, E8) and 8,192 output tokens per reply. The cache marker is the 5-minute one, on
the newest block of each request. The prompt asks the agent to work in phases (plan, rules, functions, app, review,
`agent/phases.txt`) and to call `end_phase` at the end of each.

**Two conditions**, the same in everything else, order L0 L2 L2 L0 (`order.csv`):
- **L0, no compaction:** the conversation grows inside the model's 1M-token window.
- **L2, compaction at every `end_phase`:** the harness asks the model for a summary with a fixed prompt
  (`agent/compact-prompt.txt`) and replaces the history with the task text plus that summary; the system prompt and the
  tools do not change. Our own mechanism, not the API's server-side compaction, so it is fully visible. The summary
  call counts in the attempt's cost, calls and time.

**What counts as a fix:** the mandatory checks of experiment 05 for this task (path rules; my commit's test files, 3
samples, every case must pass; one sample of each area suite, with reruns), then a review against my commit:
equivalent / valid count, worse does not. The review was delegated to Codex and approved by me; it is not strictly
blind (E11).

**The smoke** (one L0 attempt, not data) stopped at its US$ 2 cap after 65 model calls; its request log, as the gateway
recorded it, is the trajectory of the replays (E7).

**The replays** (`cases/replay.py`): the first 20 requests of that log, replayed once per condition with one change
each, `max_tokens` 0, so only the input is read or written and no output is billed: R0 control, R1 a time line in the
system prompt, R2 the tool order swapped every other request, R3 the effort setting changed once, R4 three 6-minute
pauses (simulated: the harness sleeps), R4-1h the same with the 1-hour cache lifetime, R5 an old reminder deleted from
the history, R5-sys the reminder kept and the new instruction appended as a system message.

## Reading the numbers
```
cd report
python3 ../capture/show_results.py live      # the 4 live attempts: how each ended, my tests, minutes, US$, calls, prompt, cache share
python3 ../capture/show_results.py split     # each attempt's cost: read from the cache, written, output
python3 ../capture/show_results.py replays   # the 8 replays: US$, × the control, read share
```
These are the scripts that printed the terminal tables in the video.

| File | What it is |
|---|---|
| `report/v1-live.json` | per live attempt: outcome, validator verdict, calls, tool calls and errors, minutes, US$, largest prompt, cache share, re-reads, and each compaction with the errors of the 20 calls before and after |
| `report/v1-calls.csv` | one row per model call: attempt, condition, role (`single` or `compact`), prompt size, uncached input, cache write, cache read, output, US$, seconds since the start |
| `report/c1-replays.jsonl` | one row per replayed request (cache write 5 min / 1 h, cache read, US$), and the gateway's total per replay |
| `report/c1-replays-summary.md` | the replays table, with the notes written next to the numbers |
| `tasks.csv`, `order.csv` | the task (commit, snapshot, areas, case counts) and the order of the live attempts |

## Running the harness
It needs a private app with the same shape (Flutter client, Firebase back end, Jest tests run against the emulators)
and its own `tasks/` folder; the VM scripts are in `infra/`. The scripts read the GCP project from `AIP_PROJECT` and
never use the gcloud default; the provider key goes from standard input straight into a cluster Secret. Local tests:
`python3 agent/test_agent.py`, `python3 executor/test_executor.py`, `python3 gateway/test_budget.py`,
`python3 -I infra/test_team.py`, `python3 -I infra/test_attempt.py`, `python3 cases/test_replay.py` (24, 76, 31, 29, 5
and 18 checks, all passing on the public copy).
