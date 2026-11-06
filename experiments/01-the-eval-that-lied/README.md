# agent-eval-go

A ~200-line doc-QA agent in Go, an eval for it, and the story of the eval reporting a regression that was not there.

This is the code behind the video *"My AI agent eval reported a regression that didn't exist (540 runs, 1 word)"*
(https://youtu.be/GPKgb4FtGU4). Two "harmless" changes (a cheaper model, a one-line prompt tweak) were scored by a
substring grader; the eval said the prompt tweak cost almost 4 points. Reading the failures showed every one was a
correct "not in the docs" refusal phrased with *don't*, which the grader did not accept: the regression was the
grader's, not the agent's. Nothing is mocked: every run is a real call to the Claude API, and the numbers in the
video come from `results/`.

## What is in here

| Path | What it is |
|---|---|
| `main.go` | The agent (model → tool → model loop, two tools) and the eval runner in one file |
| `gen_corpus.py` | Generates the fictional product docs (`corpus/`) and both answer keys (`questions.v1.jsonl` = grader v1, `questions.jsonl` = grader v2) from one facts table |
| `corpus/` | 17 markdown pages for "Relayline", a made-up webhook relay service, including a deprecated pricing page and a changelog as distractors |
| `questions.jsonl` | 60 questions: 40 single-fact lookups, then stale-vs-current, arithmetic, negation, not-in-the-docs, and multi-hop |
| `run.sh` | Runs one configuration with the API key read from the macOS keychain |
| `results/` | One JSONL per configuration, one line per (question, run) |

## The three configurations

| Key | Model | Prompt | Why it is in the test |
|---|---|---|---|
| A | `claude-sonnet-5-5` | base | baseline |
| B | `claude-haiku-5-5` | base | the "harmless" model swap to cut cost 20× |
| C | `claude-sonnet-5-5` | base + "Be concise. Answer in one short sentence." | the "harmless" prompt tweak |

## Reproduce the numbers offline (no API key, no cost)

The saved answers of the run shown in the video are in `results/rec-{A,B,C}.jsonl` (grader v1 verdicts). Re-scoring
them with grader v2 is a pure re-read of the files:

```bash
go build -o agent-eval-go .
./regrade.sh                      # rec-A/B/C.jsonl -> rec-A/B/C.v2.jsonl: 174/173/167 -> 180/180/180 of 180
./group.sh results/rec-A.jsonl results/rec-B.jsonl results/rec-C.jsonl   # v1 failures per question id (all q50-q54)
./show.sh results/rec-C.jsonl q52 1                                       # one failure next to the expected string
./answers.sh results/rec-A.jsonl q53                                      # every run's answer to one question
./cost.sh results/rec-A.jsonl results/rec-B.jsonl results/rec-C.jsonl    # 540 runs, $2.47
```

`python3 gen_corpus.py` regenerates `corpus/`, `questions.v1.jsonl` (grader v1) and `questions.jsonl` (grader v2)
from the facts table; the committed files are exactly what it writes, so running it is optional.

## Run new evaluations (real API calls, about $2.50 for all three configurations)

```bash
export ANTHROPIC_API_KEY=...     # or use ./run.sh, which reads the macOS keychain
./run.sh A 3                     # -> results/A.jsonl (3 runs x 60 questions, grader v2 verdicts)
./run.sh B 3
./run.sh C 3
./run.sh A 3 4 questions.v1.jsonl results/A.v1.jsonl   # the same with grader v1, to see the false regression yourself
./regrade.sh results/A.v1.jsonl results/B.v1.jsonl results/C.v1.jsonl   # re-score YOUR runs with grader v2
go run . -summary results/A.jsonl results/B.jsonl results/C.jsonl
./ask.sh "What does the Starter plan cost per month?" A   # one question, tool calls shown
./failures.sh results/C.v1.jsonl                           # 1. filter: only the failed runs
```

The helper scripts call the `agent-eval-go` binary (`go build -o agent-eval-go .`); it is not committed. `regrade` refuses to score a run whose question id is missing from the answer key.

## What the eval measures

Per (question, run): pass/fail, number of model calls (steps), input and output tokens, wall-clock
latency, cost in USD at list price, and any HTTP error. The summary prints pass rate, errors, p50
latency, average steps, tokens per run and **dollars per 100 answers**.

Grading is deliberately dumb: the answer must contain one of the expected strings (case-insensitive,
alternatives separated by `|`). Dumb graders are cheap, deterministic and easy to argue with, which is
the point: you can read every failure and decide whether the agent or the grader was wrong.

## What the eval does not catch

- Correct answers phrased without the expected token (grader false negative). Read the failures.
- Facts that are wrong in the corpus. The corpus and the answers come from the same table, so they
  cannot disagree, which also means this eval never tests "the docs are wrong".
- Anything about tone, length or formatting unless a question asks for it.
- Regressions outside these 60 questions. Add the questions your users actually ask.

## Why "write the eval before the prompt"

Monitoring tells you when the agent is down. It does not tell you when the agent is wrong.
Error rate, latency and token counts all stay green while answers get worse. The only signal that
moves is a pass rate on questions with known answers, and you only have that if you wrote it down
before you changed something.
