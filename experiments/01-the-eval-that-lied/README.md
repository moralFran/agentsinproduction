# agent-eval-go

A ~200-line doc-QA agent in Go, and the eval that tells you when it quietly got worse.

This is the code behind the video *"My agent got worse and nobody noticed"*. Nothing is mocked:
every run is a real call to the Claude API, and the numbers in the video come from `results/`.

## What is in here

| Path | What it is |
|---|---|
| `main.go` | The agent (model → tool → model loop, two tools) and the eval runner in one file |
| `gen_corpus.py` | Generates the fictional product docs (`corpus/`) and the eval set (`questions.jsonl`) from one facts table |
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

## Run it

```bash
python3 gen_corpus.py            # writes corpus/ and questions.jsonl
export ANTHROPIC_API_KEY=...     # or use ./run.sh, which reads the macOS keychain
go run . -config A -runs 3       # results/A.jsonl
go run . -config B -runs 3
go run . -config C -runs 3
go run . -summary results/A.jsonl results/B.jsonl results/C.jsonl
```

Reading the failures (the five-minute method) and the other things shown in the video:

```bash
./ask.sh "What does the Starter plan cost per month?" A   # one question, tool calls shown
./failures.sh results/C.jsonl                              # 1. filter: only the failed runs
./group.sh results/A.jsonl results/B.jsonl results/C.jsonl # 2. group: failures per question id
./show.sh results/C.jsonl q52 1                            # 3. open one answer next to the expected string
./answers.sh results/A.jsonl q52                           # every run's answer to one question
./regrade.sh                                               # re-score saved answers with questions.jsonl (grader v2), no API calls
./cost.sh results/A.jsonl results/B.jsonl results/C.jsonl  # runs and total cost
```

`go build -o agent-eval-go .` first (the scripts call the binary; it is not committed).

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
