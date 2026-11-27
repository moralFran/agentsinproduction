# Results · Experiment 06 · Long agent sessions and the prompt cache

One long task (task 8 of [experiment 05](../05-one-agent-or-a-team): the "notify me when a spot opens" alert, my
commit changed 24 files across security rules, back-end functions and the Flutter app), one agent, Sonnet 5.5, two
conditions with two attempts each, and eight replays of recorded requests to break the cache on purpose. Rules and every
amendment: [`criteria.md`](criteria.md). Every number below is computed from [`report/`](report).

**Spend.** Model calls: US$ 16.10 of a US$ 20 budget (smoke 1.29, replays 2.54, live attempts 12.27 including the
crashed attempt that was redone, 1.26). The budget was raised from the channel's default of US$ 15 for this experiment
only, before any live attempt (E8). Cloud VM: US$ 3.93 at list price.

## 1 · Does compacting make the agent forget the task?

| attempt | ended | min | US$ | model calls | compactions | largest prompt | mean prompt | input from cache | my tests | review |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| no compaction, run 1 | finished (work, review, fix) | 32.0 | 2.90 | 119 | 0 | 245,041 | 137,432 | 98.5% | passed | worse |
| no compaction, run 2 | run budget | 35.0 | 2.88 | 113 | 0 | 252,254 | 132,741 | 98.3% | rejected: touches a scratch test file | not reviewed (rejected) |
| compacted, run 1 | 40-minute clock | 39.0 | 2.70 | 129 | 3 | 180,034 | 82,733 | 97.1% | passed | worse |
| compacted, run 2 (redo) | 40-minute clock | 39.0 | 2.53 | 126 | 4 | 171,021 | 73,638 | 96.6% | passed | worse |

- **Fixes: 0 of 4.** Three patches passed my tests (my commit's tests, 3 samples, plus one sample of each area suite,
  with reruns). The fourth was rejected before any test: the budget cut it in the app phase, before the review phase
  where the prompt asks for scratch files to be removed, and it had left a scratch test file of its own (E10).
- **The review rejected all three.** Codex, by my delegation, compared each patch with my commit and ran small directed
  scenarios on both (20 scenarios, in a container with no network and stubbed dependencies): when the capacity limit of
  a recurring event is removed, my commit notifies the people subscribed to a date right away; none of the three
  patches does (a later periodic job may still send that alert; the review does not claim it never goes out). A capacity raise between two numbers works in all four. The task text the agent got asked for capacity
  raises to notify the per-date subscribers; my tests did not cover removing the limit. Each of the two compacted
  patches also has its own gap in recovering a security token; with two attempts per condition, that is one
  observation, not a measured difference (E11).
- **So, on this task, compaction did not change the result:** the patch that never compacted missed the same
  requirement as the two compacted ones (two attempts per condition). What compaction did change is below: more failed
  commands right after each compaction, and the clock.
- The review is **not strictly blind**: a diagnostic output showed the reviewer which condition one packet came from
  before it recorded its verdicts (the decisive reviews and scenarios came before). The key was not opened until all
  verdicts were in; I approved the verdicts (E11).

**Re-reads and tool errors.** A re-read is a read of a file the attempt already read and has not touched since
(`cases/rereads.py`, fixed before the first attempt). It is not a mistake by itself: after a compaction the summary may
have dropped that file. "Exited with an error" counts every command with a non-zero exit code, failing test runs
included.

| attempt | file reads | re-reads | re-reads after a compaction | tool calls | exited with an error |
|---|---:|---:|---:|---:|---:|
| no compaction, run 1 | 88 | 44 (50%) | 0 | 122 | 16 (13%) |
| no compaction, run 2 | 81 | 40 (49%) | 0 | 119 | 13 (11%) |
| compacted, run 1 | 89 | 46 (52%) | 46 | 135 | 13 (10%) |
| compacted, run 2 (redo) | 88 | 46 (52%) | 45 | 129 | 16 (12%) |

Around each compaction, the commands of the 20 model calls before and after (the windows of the last two compactions of
run 2 overlap: the agent ended a phase right after a compaction):

| attempt | at model call | prompt before | summary (chars) | errors in the 20 calls before | errors in the 20 calls after |
|---|---:|---:|---:|---:|---:|
| compacted, run 1 | 7 | 16,803 | 7,453 | 1 of 6 | 0 of 22 |
| compacted, run 1 | 43 | 95,595 | 8,892 | 0 of 20 | 2 of 22 |
| compacted, run 1 | 122 | 179,415 | 10,837 | 4 of 19 | 1 of 8 |
| compacted, run 2 (redo) | 7 | 22,303 | 9,226 | 0 of 7 | 1 of 22 |
| compacted, run 2 (redo) | 37 | 78,329 | 6,740 | 1 of 19 | 4 of 22 |
| compacted, run 2 (redo) | 110 | 170,379 | 10,609 | 3 of 19 | 4 of 14 |
| compacted, run 2 (redo) | 114 | 11,578 | 7,045 | 1 of 17 | 4 of 12 |

Errors rose after 5 of the 7 compactions and fell after 2. A compaction always lands right after a phase ends, and a
new phase can bring failing test runs of its own, so the same windows at the same points of the attempts without
compaction are the control (E15, `cases/phase_errors.py`, `report/v1-phase-errors.json`; added after the runs):

| attempt | phase end, at model call | errors in the 20 calls before | errors in the 20 calls after |
|---|---:|---:|---:|
| no compaction, run 1 | 7 | 1 of 7 | 0 of 21 |
| no compaction, run 1 | 34 | 2 of 20 | 3 of 20 |
| no compaction, run 1 | 108 | 5 of 19 | 1 of 7 |
| no compaction, run 1 | 110 | 3 of 18 | 1 of 7 |
| no compaction, run 2 | 15 | 1 of 15 | 1 of 20 |
| no compaction, run 2 | 37 | 2 of 20 | 2 of 20 |

| | points | errors before | errors after | rose / fell / same |
|---|---:|---:|---:|---|
| no compaction | 6 | 14 | 8 | 1 / 3 / 2 |
| compacted | 7 | 10 | 16 | 5 / 2 / 0 |

At the same points, errors went down without compaction and up with it. Over the whole attempt, the error rates were the
same (table above). The signal is small: two attempts per condition, windows that are not independent, and failing test
runs counted as errors. An exact permutation test on the per-point change gives one-sided p = 0.08, a measure of size, not a
significance claim. Reading, for this task: right after a compaction, more commands failed.

**Time.** Both compacted attempts ran into the 40-minute clock (run 1 in its review phase, run 2 in the fix step after
its review); the only attempt that finished on its own never compacted, in 32 minutes (two attempts each).

## 2 · What a cache hit costs

Cost parts recomputed from each call's usage at Sonnet 5.5 list prices (US$ 2 per million input tokens, cache reads
US$ 0.10, 5-minute cache writes US$ 2.50, output US$ 10); they match what the gateway booked to the cent.

| attempt | read from the cache | written to the cache | output | uncached input | total | cache read, share | US$ per request |
|---|---:|---:|---:|---:|---:|---:|---:|
| no compaction, run 1 | 1.61 | 0.61 | 0.68 | 0.000 | 2.90 | 56% | 0.0244 |
| no compaction, run 2 | 1.47 | 0.63 | 0.78 | 0.000 | 2.88 | 51% | 0.0255 |
| compacted, run 1 | 1.04 | 0.77 | 0.88 | 0.001 | 2.70 | 38% | 0.0209 |
| compacted, run 2 (redo) | 0.90 | 0.79 | 0.85 | 0.001 | 2.53 | 35% | 0.0201 |

Without compaction, 98% of the input came from the cache, and reading it back was still the biggest line of the bill
(56% and 51%): every request sends the whole conversation again, and the conversation grew to about 250k tokens.
Compaction cut the average prompt from about 135k to about 78k tokens and the cost per request from about 2.5 to about
2 cents, but every summary starts a new conversation that is written to the cache again (cache writes US$ 0.77 and
0.79 against 0.61 and 0.63), the compacted attempts made more model calls, and neither of them finished.

## 3 · What breaks the cache (replays)

The first 20 requests of the smoke attempt's recorded log (prompts of 5,866 to 46,169 tokens), replayed once per
condition with one change each, `max_tokens` 0 (no output billed: these are input costs only). Each replay starts its
system prompt with its own id, so none reads another's cache. Every request answered 200.

| replay | what changes | US$ | × control | written (5 min) | written (1 h) | read | read share |
|---|---|---:|---:|---:|---:|---:|---:|
| R0 | control: nothing changed | 0.1602 | 1.0 | 46,166 | 0 | 447,300 | 90.6% |
| R1 | a 'Current time: hh:mm:ss' line at the end of the system prompt, new at every request | 0.9753 | 6.1 | 385,752 | 0 | 107,934 | 21.9% |
| R2 | the two tools in reversed order on every even request | 0.2601 | 1.6 | 87,782 | 0 | 405,684 | 82.2% |
| R3 | effort set to medium from request 11 on (default high) | 0.2226 | 1.4 | 72,158 | 0 | 421,308 | 85.4% |
| R4 | 6-minute pauses before requests 6, 11 and 16 (simulated) | 0.3296 | 2.1 | 116,728 | 0 | 376,738 | 76.3% |
| R4-1h | R4 with every cache marker at ttl 1h | 0.2295 | 1.4 | 0 | 46,169 | 447,357 | 90.6% |
| R5 | the request-5 reminder deleted from the history from request 11 on | 0.2002 | 1.2 | 62,838 | 0 | 430,388 | 87.3% |
| R5-sys | the reminder kept; a role:system message with the instruction after request 11's user turn | 0.1603 | 1.0 | 46,187 | 0 | 447,501 | 90.6% |

- **R1** sends a request about every second; when two consecutive requests fell in the same second the time line did
  not change and the cache was read. In a live session the line changes at every request.
- **R2:** each tool order keeps its own cache entry, so alternating orders read the entry of two requests back.
- **R5:** the edited history was accepted with no error on this account: the break is silent. From request 11 the read
  stops at the prefix before the reminder (9,296 tokens) and the rest is written again once.
- **R4-1h:** no rewrite after the pauses; the price is every write at 2× the input instead of 1.25×. Here 1.4× against
  R4's 2.1×; in a session where the prefix always comes back within five minutes, it only costs more. The five minutes
  count from the start of a request, so a slow reply counts too.
- **R5-sys:** the instruction appended as a system message keeps the prefix: 1.0×, the same as the control.

## Limits
- One app, one long task, one model (Sonnet 5.5), my own harness, two attempts per condition.
- One compacted attempt was redone because the harness crashed on a byte that was not valid UTF-8 (E9); the crashed try
  is kept in the private record and its cost is in the total.
- One attempt without compaction stopped at its run budget with US$ 1.12 of it unspent: the gateway reserves each call's
  worst case before sending it, and that reservation counts the input as request bytes / 2 (about twice the real
  tokens of this repository's text) and prices all of it as a cache write, when almost all of it was a cache read. Its
  last calls really cost US$ 0.03 to 0.05; the next one reserved US$ 1.13. The reservation grows with the prompt, so it
  weighs more on the condition without compaction (E9, E13).
- The reminder of request 5 stayed in the context for the whole L0 sessions but only until the first compaction (call 7)
  in L2: compaction replaces the history with the task text and the summary (E13).
- Only the newest block carries a cache marker, so after each compaction the tools and the system prompt were written
  to the cache again (cents per compaction; E13).
- Two harness gaps found after the collection by an external review (E14), fixed for future runs with tests: a Jest
  process killed by a signal after writing a report of passing cases counted as passing (in the Jest samples kept,
  18 validation samples with 594 processes and 10 control samples with 378, every exit code was 0 or 1), and a `git commit` made by the agent would have hidden its patch (none of
  the 632 logged commands, smoke and voided try included, runs `git commit`; 186 are cut at 400 characters).
- Automatic compaction (above a fixed size) and a project guide split into folders were not tested: they did not fit
  the budget (E1). The guide was not in the system prompt in any attempt (E7).
- The cache breaks were measured by replaying recorded requests, once each, input only; the pauses were simulated.
- Claude Code was not tested. The numbers from my own Claude Code sessions that open the video chose the questions;
  they are not data of this experiment.
- The review was done by another model (Codex) by my delegation and approved by me, not strictly blind (E11).
