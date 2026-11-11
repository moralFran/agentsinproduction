# Agents in Production

Code, data and results behind the videos on the **Agents in Production** YouTube channel: real experiments with
AI agents, run for real, with the numbers you see on screen.

| # | Video | Folder |
|---|---|---|
| 01 | [My AI agent eval reported a regression that didn't exist (540 runs, 1 word)](https://youtu.be/GPKgb4FtGU4) | [`experiments/01-the-eval-that-lied`](experiments/01-the-eval-that-lied) |
| 02 | [I poisoned my AI agent's docs. My tests didn't notice.](https://youtu.be/wfrVLXcVJLo) (Nov 12, 2026) | [`experiments/02-poisoned-docs`](experiments/02-poisoned-docs) |
| 03 | I gave my coding agent a shell. Then tested the sandbox. (video coming) | [`experiments/03-sandbox-boundaries`](experiments/03-sandbox-boundaries) |

Each experiment folder has its own README with how to run it, the question set, the grader(s), the saved raw
answers of every run and a `results.md` with the numbers and their limits.

Secrets never live in this repo: the scripts read the API key from the macOS keychain (`run.sh`), from the
`ANTHROPIC_API_KEY` environment variable, or (experiment 03) from standard input straight into a cluster Secret.

License: MIT.
