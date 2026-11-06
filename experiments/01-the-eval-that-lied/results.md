# Results — run of 2026-11-04

60 questions × 3 runs × 3 configurations = 540 agent runs, all real API calls. Raw per-run data in
`results/*.jsonl` (kept out of git). Total API cost of the whole experiment: **$2.44**.

## Headline table (grader v1, the one the experiment started with)

| config | model | runs | pass rate | HTTP errors | p50 latency | avg steps | $ per 100 answers |
|---|---|---|---|---|---|---|---|
| A-sonnet-base | claude-sonnet-5-5 | 180 | 96.1% | 0 | 4.9 s | 2.42 | $0.735 |
| B-haiku-base | claude-haiku-5-5 | 180 | 96.1% | 0 | 3.1 s | 2.62 | $0.041 |
| C-sonnet-concise | claude-sonnet-5-5 | 180 | **92.2%** | 0 | 4.0 s | 2.26 | $0.582 |

Reading this table, the "harmless" model swap (B) held and the "harmless" prompt tweak (C) regressed by
four points. Zero errors, latency fine, in every configuration.

## What the failures actually were

Run 1 (04/11): 27 of the 28 failures, across all three configurations, were on the five "not in the docs"
questions (q50–q54: refund policy, SMS delivery, support phone number, internal database, headcount). The 28th
was Haiku, run 1, q49 (SSO on Starter): a correct answer ("available on the **Growth** plan") whose markdown
bold markers break the substring `growth plan`; it stays a "failure" under grader v2 too, hence Haiku's 179/180.
Reading the 27 q50–q54 answers: **all 27 were correct refusals**. The agent said "The docs don't say…" or
"I couldn't find…". The grader accepted `not`, `no information`, `doesn't`, `does not`, `unable`, and none
of those is a substring of *don't* or *couldn't*. The "regression" in C was the concise prompt making the
model prefer "The docs don't say" over the longer phrasings that happened to match.
Run 2 (05/11, the run in the video): all 26 failures were on q50–q54 and all pass under grader v2 (180/180 ×3).

## Corrected table (grader v2: refusal phrasings added)

| config | grader v1 | grader v2 | p50 latency | $ per 100 answers | total $ |
|---|---|---|---|---|---|
| A-sonnet-base | 96.1% | **100.0%** | 4.9 s | $0.735 | $1.32 |
| B-haiku-base | 96.1% | **99.4%** | 3.1 s | $0.041 | $0.07 |
| C-sonnet-concise | 92.2% | **100.0%** | 4.0 s | $0.582 | $1.05 |

The one remaining Haiku "failure" under grader v2 (q49, run 1) is also the grader: the answer says SSO is
available on the "**Growth** plan" and the markdown bold markers break the substring `growth plan`.
So in run 1 Haiku did not tie Sonnet exactly on the revised grader (179/180 vs 180/180); in substance, every
answer I inspected was correct. Run 2 scored 180/180 in all three configurations.

## What this means

1. Neither "harmless" change regressed on this eval. Haiku came within a point of Sonnet's **pass rate on this grader**
   (run 1: 179/180 vs 180/180 under grader v2; run 2: 180/180 both) at 18× lower cost and 37% lower latency, on a
   corpus of 17 pages. That does not establish equal answer quality: a substring
   grader only checks that the expected string is present. Example: q38 (Haiku, run 1) correctly says audit logs are
   kept 365 days, then adds that event bodies are deleted after those 365 days, while the docs say events live 3 days
   (Free) or 30 days (paid); it passes because "365" is there (`results/rec-B.jsonl:39`, `corpus/09-retention.md`).
   (And it is one data point; it does not generalize to harder corpora.)
2. The eval produced a **false regression** of 4 points on C. If this were a dashboard, someone would have
   rolled back a prompt that was fine, or worse, "fixed" the model into matching the grader.
3. The failure mode of a dumb grader is systematic, not random: it hit exactly one category of question
   in exactly one direction. Reading the failures took about five minutes (an estimate, not a measured time) and reversed the conclusion.
4. Variance across the 3 runs was small: the same questions failed every time. A pattern that tight says where
   to look first (the answer, the retrieved docs, the grader); it does not by itself show which one is wrong. Here,
   opening the answers is what showed the grader was the problem.

## Run 2 — 2026-11-05, the run shown in the video (A-v03)

Same code, same corpus, same 60 questions, re-run on camera with grader v1 (`questions.v1.jsonl`, 6 workers), then
re-scored with grader v2 (`./regrade.sh`, no API calls). Raw data in `results/rec-{A,B,C}.jsonl` and `.v2.jsonl`.
Total API cost of the three runs: **$2.47** (540 runs).

| config | grader v1 | failures v1 | grader v2 | p50 latency | $ per 100 answers |
|---|---|---|---|---|---|
| A-sonnet-base | 96.7% | 6 | **100.0%** | 4.2 s | $0.771 |
| B-haiku-base | 96.1% | 7 | **100.0%** | 2.7 s | $0.041 |
| C-sonnet-concise | **92.8%** | 13 | **100.0%** | 3.2 s | $0.563 |

Every v1 failure, in all three configurations, was again on q50–q54 (the "not in the docs" questions) and every one
was a correct refusal phrased with "don't" / "couldn't". Under grader v2 there were no failures left at all (run 1 had
one markdown-bold false negative; run 2 had none). Haiku vs Sonnet: 19× cheaper per 100 answers
(−95%), 35% lower p50 latency (unrounded medians). The "regression" of C was 3.9 points.

Known limitations of the question set: q56 asks for the longest total retry time but accepts any answer containing
"hour", and the docs do not give the backoff multiplier, so q56 does not validate the arithmetic it asks for. The
benchmark supports the false-regression finding (every v1 failure was a correct "not in the docs" refusal); it does
not support claims about reasoning quality.

Run 1 (04/11) and run 2 (05/11) agree on every conclusion; the pass rates moved by less than a point between runs,
which is the expected noise of 180 samples per configuration.

## Reproduce

```bash
python3 gen_corpus.py && ./run.sh A 3 && ./run.sh B 3 && ./run.sh C 3
go run . -summary results/A.jsonl results/B.jsonl results/C.jsonl
```

`questions.jsonl` now ships with grader v2. To reproduce the v1 numbers, replace the `expected_contains`
of q50–q54 with `not|no information|doesn't|does not|unable`.
