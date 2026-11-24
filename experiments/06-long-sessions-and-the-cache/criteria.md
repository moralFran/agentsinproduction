# Experiment 06 · V7 · A-v08 · long sessions and the prompt cache: criteria (written before any collection)

Source protocol: `assets/roteiros/A-v08-narracao.template.md` (draft 1, 12/11/2026, structure approved by Francisco),
with the **amendment of 23/11/2026** (Francisco chose the reduced scope to fit the US$ 15 ceiling). This file records
the protocol as run and every later change, dated. Private (task paths appear in the code it points to).

## E1 · Scope (23/11/2026, before any model call)
- **Live attempts:** task 8 of experiment 05 (commit `a06f707b`, parent `9928e447`), one agent (configuration A of
  experiment 05), Sonnet 5.5. Two conditions, two attempts each, order **L0 L2 L2 L0** (`order.csv`):
  - **L0** no compaction;
  - **L2** planned compaction at every `end_phase` (harness summary with `agent/compact-prompt.txt`, history replaced
    by task + summary, same system and tools).
  L1 (compaction above a fixed size) and L3 (guide split into folders) are **not run**: the video says they were not
  tested.
- **Smoke:** one L0 attempt with the same settings; it is not live data. Its request log is the **trajectory** of the
  reproductions.
- **Reproductions:** R0, R1, R2, R3, R4, R4-1h, R5 and R5-sys, **one each**, K = 20 requests of the trajectory
  (`cases/replay.py`; pauses and the change point at requests 6, 11, 16). If R5 is refused by the API (an edited history
  on an account where the history-editing check is enforced), that refusal is the result, and **R5-drop** (the same
  edit with `prefix_mismatch_behavior: drop_block`) measures the cache effect. The "how to find it" segment (cache
  diagnostics header) runs only if the budget is left after everything else.

## E2 · Settings shared by every live attempt (and the smoke)
- Model `claude-sonnet-5-5`, default temperature, thinking and effort not set (the model's defaults: adaptive thinking,
  effort high).
- Limits: 40 min wall clock (cooperative 2,340 s, pod deadline 2,460 s), 150 tool calls, **US$ 2.00 per attempt**
  (gateway run cap), **8,192 output tokens per reply** (experiment 05 used 4,096 and two of its task-8 attempts stopped on
  it). The cap reserves each call's worst case before sending it (as in experiment 05: that reservation grows with the
  conversation; the video says so if it decides an attempt).
- System prompt: attempt id first; project notes; the single-agent prompt; the phases prompt (`agent/phases.txt`); the
  snapshot's `CLAUDE.md` whole ("monolithic guide"). The same bytes in every request of an attempt.
- The reminder of request 5 (`agent/agent.py`, REMINDER) in both conditions, appended after the tool results, never
  removed.
- Cache breakpoint: `ephemeral` (5 min) on the last block of the last message; nothing else.

## E3 · What counts as a fix
The mandatory checks of experiment 05 for task 8 (validator path rules; the commit's tests pass 3/3; the suites of the
three areas pass 3/3, run by the executor outside the agent's pod), then a blind verdict (equivalent / valid / worse /
inconclusive) by the same judge as experiment 05 unless Francisco says otherwise. Inconclusive never counts as a fix.

## E4 · Budget
- Gateway total budget **US$ 15** (smoke, live, reproductions, retries: everything). Run caps: US$ 2 per live attempt
  and smoke; up to US$ 3 per reproduction.
- Estimate before the smoke (from experiment 05's task-8 numbers): ~US$ 2 for a complete attempt; reproductions with
  `max_tokens: 0` (no output billed) ~US$ 4–6 in all, R1 and R2 (everything rewritten at every request) being most of
  it. If the smoke shows the plan cannot fit, the options go to Francisco before any live attempt.
- GCP: VM `aip-ctx-01` (n2-standard-8), logged in `tracking/creditos.csv`, deleted when he authorizes.

## E5 · Measurements
- Live: fix (E3); tokens and US$ per call (`calls` in the agent's RESULT); prompt size curve; compactions (when, prompt
  size before, summary size); re-reads (`rereads.py`, written before the first live attempt); tool errors in the 20 calls
  after each compaction vs the 20 before; time.
- Reproductions: per request, uncached input, cache writes (5 min and 1 h), cache reads, US$; the total against R0.

## E5a · Reporting rules
- Two attempts per condition: a difference inside their spread is "I can't tell them apart".
- Pauses are simulated; cache breaks were measured in reproduction, not with a live agent; one app, one model, one task.
- Claude Code was not tested; the owner's own session numbers only chose the questions.

## E6 · Task 8 in this lab (23/11/2026, written while its check ran, before any result)
- The snapshot built here is byte-identical to experiment 05's (git archive sha256 `fd6c508d…`, same as its
  `tasks/cases/T8.json`), and so are the dependency sets (`pub-0c5fce4b3d`, `node-1c6c4a0b89`, pubspec.lock
  `2c9033da…`). The box image was rebuilt from the same Dockerfile with the same tool versions.
- So experiment 05's F2P/P2P lists for task 8 (3 baseline + 3 gold samples: 204 F2P, 13,145 P2P) are reused, **if** one
  baseline and one gold sample of every job on this lab agree with them (`cases/check_v6_lists.py`: every F2P case fails
  on baseline and passes on gold, every P2P case passes on both). If any case disagrees, the full 3 + 3 reproduction
  runs and its lists are used instead. The agent's failure text comes from this lab's baseline sample.

## E7 · Smoke result and what it changes (23/11/2026, before any live attempt or reproduction)
- Smoke `quote-1-t8-l0-r1` (L0, cap US$ 2): **budget_exhausted** after 65 model calls, 70 tool calls, 22.5 min,
  US$ 1.2931 booked. Phases ended at calls 11 (plan), 14 (rules) and 36 (functions); the app and review phases were not
  reached. Prompt size: 5,866 tokens at call 1, 81,909 at call 31, 163,950 at call 65. Cache reads were 96.9% of the
  input. The stop: the next call reserved US$ 0.7346 with US$ 0.7069 left (the cap reserves the worst case; at ~164k
  tokens of prompt that is ~US$ 0.73).
- **The project guide was not in the system prompt.** The snapshot leaves `CLAUDE.md` out (experiment 05's E4
  exclusions), so the agent's guide text was "(the repository has no CLAUDE.md)". E2's "monolithic guide" does not hold:
  the system prompt is the harness's own (~3.3k characters). With L3 dropped the guide is not a variable of this
  experiment; it stays out for every live attempt, so all of them share the smoke's system prompt.
- The trajectory of the reproductions is the smoke's request log (65 requests, all 200; the reminder at request 5;
  K = 20 covers prompts of 5,866 to 46,169 tokens). Estimate for the 8 reproductions: ~US$ 3.3 (R1 ~1.24, R2 ~0.7).
- The live plan (4 attempts at US$ 2) cannot show an L0 attempt finishing: L0 needs ~US$ 3 or more for task 8. The
  options go to Francisco before any live attempt; the reproductions run first (already in the approved scope).

## E8 · Ceiling raised for this experiment (Francisco, 23/11/2026, after the smoke, before any live attempt)
Options shown to him: 4 attempts at US$ 2.60 inside US$ 15 (L0 would stop before finishing), US$ 20 with US$ 4 per
attempt, or 2 attempts at US$ 4.50. **He chose "Subir o teto para US$ 20".** So: gateway total budget US$ 20 (everything
already spent included), run cap **US$ 4 per live attempt**, same order L0 L2 L2 L0, nothing else changes. The gateway
is restarted with BUDGET_USD=20 and MAX_RUN_USD=4 after the reproductions end (its state, with the spend so far, is
kept on its volume). An exception for this experiment only; the US$ 15 rule stays the default.

## E9 · The four live attempts, and the harness crash of L2 r2 (23/11/2026, ~18:45 UTC, before any patch is validated)
No verdicts here: none of the four patches has been validated (`VALIDATE=0`); the validator runs only after the decision
below.

| attempt | ended by | model calls | min | US$ | largest prompt | phases ended | compactions (at call, prompt before) |
|---|---|---|---|---|---|---|---|
| v1-t8-l0-r1 | finished (work, review, fix) | 119 | 32.0 | 2.90 | 245,041 | 4 | none |
| v1-t8-l2-r1 | 40-min clock, in the review phase | 129 | 39.0 | 2.70 | 180,034 | 3 | 7 (16,803), 43 (95,595), 122 (179,415) |
| v1-t8-l2-r2 | **harness crash** (below), in the app phase | 70 | 21.4 | 1.26 | 90,859 | 2 | 7 (20,409), 33 (81,278) |
| v1-t8-l0-r2 | run cap, in the app phase | 113 | 35.0 | 2.88 | 252,254 | 2 | none |

- **L0 r2** stopped on the US$ 4 cap: the next call reserved US$ 1.1333 with US$ 1.1169 left. The reservation counts
  the input as request bytes / 2 (gateway v3 rule), about twice the real tokens of this repository's text (a 252k-token
  prompt was reserved as ~525k), plus 8,192 output tokens; Sonnet 5.5 has one price at every prompt length, and the
  booking uses the reported usage. So the attempt stopped with US$ 1.12 of its cap unspent. E2's rule; the video says so.
- **L2 r2 crashed in the harness, not in the model path.** `bash()` in `agent/agent.py` read the command's output with
  `subprocess.run(text=True)`; one command printed a byte that is not UTF-8 (0xe2 without its continuation bytes) and
  the decode raised `UnicodeDecodeError`, which left the session and ended the attempt as `error` at call 70. The
  command was not logged (the crash came before its log line). The code is experiment 05's, unchanged.
- **Fix (`errors="replace"` on that call):** a byte that is not UTF-8 becomes U+FFFD; for valid UTF-8 the text, newline
  handling included, is identical to before (checked), so the three attempts that did not crash would have received
  the same tool results. Check 5 of `agent/test_agent.py` reproduces the crash with the old line and passes with the
  new one (24 checks).
- **Decision pending (Francisco), taken before any patch is validated:** (a) the crashed try is not an L2 result: its
  record moves to `results/voided-v1.jsonl` (`cases/void_tries.py`, nothing deleted) and L2 r2 is redone as
  `v1-t8-l2-r2-t2` with the fixed harness, cap US$ 4, nothing else running on the VM (gateway total after it at most
  US$ 17.57 of 20); or (b) it stays as an L2 attempt that ended in error (the runner's rule of 13/11: an error the pod
  reports is an attempt). Total booked by the gateway so far: US$ 13.5708 (smoke, 8 reproductions, 4 attempts).
- **Decided (Francisco, 23/11/2026, before any validation): (a), redo.** The crashed record goes to
  `results/voided-v1.jsonl` with its patch in `results/patches/v1/voided/`; L2 r2 runs again as `v1-t8-l2-r2-t2` with
  the fixed `agent.py` (config map `ci-code` rebuilt, sha256 checked), same settings as the others. Its US$ 1.26 stays
  in the experiment's total cost, and the report and the video say one L2 attempt was redone because of a harness bug.
- **Redo result (18:55–19:34 UTC):** `v1-t8-l2-r2-t2` ended on the 40-min clock in the fix step after its review (4
  phases ended, review done), 126 model calls, 129 tool calls, US$ 2.5337, largest prompt 171,021, compactions at calls
  7 (22,303), 37 (78,329), 110 (170,379) and 114 (11,578). Gateway total now about US$ 16.10 of 20. The validator
  (experiment 05's, unchanged: E10 two stages, E18, E22, E23) started at 19:34:58 UTC on the four patches, one at a
  time, nothing else running (`~/validate-v1.sh` on the VM).

## E10 · Validation of the four patches, behaviour numbers, blind packets (23/11/2026, 19:35–22:50 UTC)
- **Validator as run:** experiment 05's `cases/validate.py`, unchanged (only the host name in its docstring differs):
  stage 0 path rules; stage 1 the commit's jobs, 3 samples each (204 F2P and the P2P cases of those files); stage 2
  one sample of each area job, with reruns of any file that failed (its E10, E18, E22, E23). E3's parenthetical ("the
  suites of the three areas pass 3/3") was wrong as written: experiment 05's rule runs stage 2 once with reruns, and
  that is what ran, the same for every patch. One patch at a time, nothing else on the VM, ~57 min each.
- **Verdicts:**

| attempt | validator | decided in | F2P failed | broken in stage 2 |
|---|---|---|---|---|
| v1-t8-l0-r1 | resolved | stage 2 | 0 of 204 | 0 |
| v1-t8-l2-r1 | resolved | stage 2 | 0 of 204 | 0 |
| v1-t8-l2-r2-t2 | resolved | stage 2 | 0 of 204 | 0 |
| v1-t8-l0-r2 | **rejected_by_validator** | stage 0 | not run | not run |

- **L0 r2** left a scratch test file of its own (a `zz_scratch.test.js` among the functions tests) in the working copy;
  the path rules refuse any patch that touches a test file. The cap cut it in the app phase, before the review phase,
  where the prompt asks for scratch files to be removed. Not a fix (E3); none of its other files was run.
- **By the validator: L0 1 of 2, L2 2 of 2.** Two attempts per condition: inside the spread (E5a), "I can't tell them
  apart". A fix still needs the blind verdict (E3). Both L2 patches that passed come from attempts that ran into the
  40-min clock after their app phase (r1 in the review, r2-t2 in the fix step after its review): what was in the working
  copy at that moment passed. L0 r1 finished in 32 min.
- **Behaviour** (`report/v1-live.json`, `report/v1-calls.csv`: numbers only, no command text, no paths):
  - Largest prompt L0 245,041 and 252,254; L2 180,034 and 171,021. Booked US$ L0 2.9019 and 2.8831; L2 2.6952 and
    2.5337. A list-price recomputation from each call's usage matches the gateway to the cent.
  - Re-reads (`cases/rereads.py`, committed 14:06 UTC, before the first attempt at 16:16): L0 44 of 88 and 40 of 81
    reads; L2 46 of 89 and 46 of 88 (all but one after a compaction). Limits of the rule: another line range of the same
    file (`sed -n 1,200p` then `200,400p`) counts as a re-read, and commands are logged cut at 400 characters.
  - Tool errors (exit code not 0, failing test runs included) in the commands of the 20 model calls before and after
    each compaction: L2 r1 at call 7: 1 of 6 then 0 of 22; at 43: 0/20 then 2/22; at 122: 4/19 then 1/8. L2 r2-t2 at 7:
    0/7 then 1/22; at 37: 1/19 then 4/22; at 110: 3/19 then 4/14; at 114: 1/17 then 4/12 (110 and 114 overlap: the
    agent ended a phase right after a compaction, so the next summary started from 11,578 tokens).
- **Blind packets:** `cases/blind_team.py v1` wrote 3 packets (the 3 `resolved`), random ids, same date on every file,
  no run id, condition or repetition in any header (the script's own check: 0); key in `results/blind/key.jsonl`
  (mode 600) on the VM, not opened. The page `judge/` runs on the VM on 127.0.0.1:8796 only. Judge: as in experiment 05,
  Codex by Francisco's delegation, unless he says otherwise. Limits: (1) he and the agent know the validator's verdict
  per condition, so one of the three packets is known to be L0 and two L2, without knowing which; (2) a patch can give
  its condition away by style or size; there is no control for that.
- **Cost:** gateway total US$ 16.1046 of 20 (782 requests): smoke 1.2931, reproductions 2.5379, live 12.2736 (the
  crashed L2 r2 included). Logged in `tracking/creditos.csv` (`A-v08-coleta-v1`).

## E11 · Delegated patch review (23/11/2026, after collection and validation)

- Francisco requested review and validation of the patches. Codex recorded three `pior` verdicts
  in the judge page as `codex_delegated`; no pending packets remain. The fourth attempt retains
  its stage-0 path rejection. Mandatory validation remains 3/4; accepted fixes under E3 are **0/4**.
- The existing rubric covers omitted required behaviour outside mandatory-test coverage. A
  directed reproduction found the same omitted capacity-change notification case in all three
  packets; two also have distinct token-recovery gaps. The reference passes these scenarios.
  The new probes are review evidence, not a change to the frozen mandatory tests or generated patches.
- The 30 retained candidate sample results were independently checked against the frozen lists.
  Required cases pass in clean files. Four other files fail to run in each candidate and in the
  retained baseline/gold controls; do not describe the entire suite as clean.
- Blinding limitation: the decisive source review and reproductions preceded any condition
  exposure, but a later validation-metadata diagnostic exposed a condition-bearing identifier
  before verdict submission. Do not call the completed judgment strictly blind. The identity
  key was not opened. Reviewer is Codex by delegation, not Francisco personally.
- Aggregate report: [codex-review-2026-11-23.md](report/codex-review-2026-11-23.md).
  Detailed evidence and verdicts stay on the VM under `results/blind/codex-review-2026-11-23/`.
  No model calls, original-patch edits, VM resizing or lifecycle changes were made during review.
- **Checked by the agent (Claude) before opening the key, 23:3x UTC:** `results/blind/verdicts.jsonl` has 3 lines, one
  per packet, all `pior`, `source: codex_delegated`, reviewer Codex, all at 23:14:04 UTC. `key.jsonl` was last read at
  22:34:11.077 UTC, the moment it was written (its atime is older than its mtime, so any later read would have moved
  it): not opened. Francisco pasted Codex's report in the chat as his own message. The key is opened now.
- **Correction to what the agent told Francisco at 22:50:** "the suites of the three areas were clean" was too broad.
  Every required case passed in a clean file; four files outside the frozen lists fail to run in every candidate and in
  the baseline and reference controls alike (Codex's check above), which is why they are not in the lists.
- **Key opened (after the two points above):** 35204297 = `v1-t8-l0-r1` (L0); b8c82d73 = `v1-t8-l2-r1` (L2);
  c186c860 = `v1-t8-l2-r2-t2` (L2). So: the defect common to the three (removing the capacity limit of a recurring
  experience does not notify the per-date subscribers) is in L0 and in both L2; each L2 patch also has its own
  token-recovery gap, the L0 one does not. **Accepted fixes (E3): L0 0 of 2, L2 0 of 2.** With two attempts per
  condition and zero fixes, nothing here says one condition fixes better (E5a); the extra defects of the two L2
  patches are one observation, not a measured difference. Cost per accepted fix has no finite value in this round.

## E12 · Lab closed (23/11/2026, 23:23 UTC, Francisco: "sim ok")
- Audit record copied to the SSD: `arquivo-privado/aip-ctx-01-v07-cache-20261123.tgz` (sha256 `cec2e131…`, the same on
  the VM and on the SSD): journals (live, voided, infra, before-void and before-verdicts copies), patches (voided one
  included), verdicts, blind packets, key, Codex's review and evidence, validator and pod logs, kept samples, the
  check_v6_lists runs, the gateway's request-body log and state (token hashes removed). Not copied: the app snapshot
  (`~/input/*.tar`, `/srv/ci/cases`), `/srv/ci/secret`, the dependency caches, any key. A search of the archive for an
  API key, a run token or a token hash found none.
- VM `aip-ctx-01` and its boot disk deleted (labels `owner=aip`, `experiment=aip-ctx` checked first); nothing with the
  `aip-` prefix left in the project. GCP at list price US$ 3.93 (9.34 h), logged as `A-v08-gcp-vm`.

## Log of changes
- 23/11/2026: E11, after delegated review; mandatory pass counts unchanged, three `pior` judgments recorded.
- 23/11/2026: this file (E1–E5a), before the VM existed.
