# Experiment 05 · Results

Every number below comes from a file in this folder, named next to it. Collection: round `c1`, 2026-11-16
07:58–12:42 UTC (`report/collection/collect-c1.log`), 32 attempts (8 tasks × 2 setups × 2 repetitions), model
`claude-sonnet-5-5` in every attempt (`report/collection/attempts-c1.meta.jsonl`).

**In one line:** one agent got 7 valid fixes out of 16 attempts, the team 9 out of 16; the team cost 42% more in total
and about 10% more per fix. With 2 runs per setup, the gap is 2 cells and I can't tell the setups apart.

## 1. Per setup (`report/c1-blind.csv`, `report/c1-attempts.csv`)
`python3 ../capture/show_results.py tally` and `… cost`, from `report/`.

| | A · one agent | B · team |
|---|---|---|
| passed the validator (`resolved`) | 13 of 16 | 14 of 16 |
| blind verdict: equivalent / valid / worse | 3 / 4 / 6 | 4 / 5 / 5 |
| **fixes** (`resolved` and equivalent or valid) | **7 of 16** (3 in repetition 1, 4 in 2) | **9 of 16** (5 and 4) |
| spent (model calls) | US$ 3.99 | US$ 5.67 |
| **spent per fix** | **US$ 0.57** | **US$ 0.63** |
| model calls | 309 | 475 |
| input read from the cache | 92% | 84% |
| agent time per fix | 766 s (about 13 min) | 808 s (about 13 min) |

## 2. Per task (`report/c1-blind.csv`; `show_results.py grid`)

| Task | A (rep. 1, rep. 2) | B (rep. 1, rep. 2) |
|---|---|---|
| T1 | fix, fix | fix, fix |
| T2 | fix, worse | fix, worse |
| T3 | failed the validator, fix | fix, fix |
| T4 | worse, worse | worse, worse |
| T5 | worse, worse | worse, worse |
| T6 | fix, fix | fix, fix |
| T7 | worse, fix | fix, fix |
| T8 | failed, failed | failed, failed |

6 of the 8 tasks came out the same for both setups in both repetitions. The 7 vs 9 is two cells, both in repetition 1:
- **T3:** the single agent stopped at the limit of 4,096 output tokens per reply, after 12 model calls and before it wrote
  any file (`stopped_max_tokens` in `report/c1-attempts.csv`). That limit is the same for A and B.
- **T7:** the single agent's patch passed the tests and was judged worse.

## 3. What the team's extra cost is made of (`show_results.py cost`)
Priced as the gateway books it (Sonnet 5.5 at US$ 2 / 10 per million input / output tokens, cache writes 1.25×, cache
reads 0.05×); the script checks that the parts add up to what the gateway booked.

| | spent | cache writes | output | cache reads |
|---|---|---|---|---|
| one agent | US$ 3.99 | US$ 1.69 | US$ 1.49 | US$ 0.82 |
| team | US$ 5.67 | US$ 2.90 | US$ 2.16 | US$ 0.61 |
| **team − agent** | **+1.68** | **+1.21** | **+0.67** | **−0.20** |

The team made 166 more model calls; most of its extra cost is new context written to the cache, and extra output.

## 4. 11 of 27 passing patches were judged worse (`report/c1-blind.csv`)
27 patches passed the validator; 11 were judged worse, in both setups and mostly on the same tasks: all 8 attempts of
T4 and T5 (both setups, both repetitions), one per setup in T2, and the single agent's in T7. In the judge's notes the
recurring reason is a part of the task that my commit's tests do not cover. Example, task 4 (a chat between a host and a
guest): my commit makes the conversation read-only for both sides when the guest leaves. Three patches lock only the
guest's screen; the fourth locks both, but if the guest leaves while the host has the delete dialog open, the delete
still goes through.

The notes quote the app's code, so they are not published. I reviewed the notes for tasks 4 and 5 (8 of the 11) after
the key was opened; every verdict stayed (`criteria.md`, last sections).

## 5. Task 8: no fix, stopped by the limits (`report/c1-attempts.csv`, `report/collection/gateway-20261116T1041Z.log`)
Task 8 touches security rules, back end and the Flutter app. Neither setup fixed it:

| Run | Outcome | Spent of the US$ 0.75 cap |
|---|---|---|
| `c1-t8-a-r1` (one agent) | budget stop | US$ 0.42 |
| `c1-t8-a-r2` (one agent) | budget stop | US$ 0.43 |
| `c1-t8-b-r1` (team) | output limit (4,096 tokens per reply) | US$ 0.31 |
| `c1-t8-b-r2` (team) | budget stop | US$ 0.45 |

The budget stops came at US$ 0.42–0.45, not 0.75, because the gateway reserves the worst case of the next call before
forwarding it (its whole input, estimated from the request's size, priced as a cache write, plus the maximum output;
`gateway/gateway.py`) and refuses the call if the run's money left can't cover it. In the
gateway log of `c1-t8-a-r2` (`source ../capture/gw.sh && gw c1-t8-a-r2`):
```
refused   run budget: this call reserves $0.3330, $0.3246 left in run c1-t8-a-r2
```
A single agent's conversation keeps growing, so its next call's worst case grows with it; a team spreads the same work
over shorter conversations. So this rule weighs more on one long conversation than on several short ones.

## 6. What the whole experiment cost
- **Model calls: US$ 11.11** (`report/collection/gateway-budget.json`, 943 requests): the 32 counted attempts
  (US$ 9.67), the quote before the collection (US$ 0.73), and the tries voided by the credit incident plus infrastructure
  retries.
- **Cloud machine: about US$ 17** (US$ 16.87 at list price: `n2-standard-8` for 19.3 h, `n2-standard-32` for 5.4 h, a
  200 GB balanced disk and an external IPv4 address, from the machine's create, resize, stop and delete times).

## Limits
- 8 tasks from one app I know well, one model, 2 runs per setup, my own commits as the answer key.
- The blind judge is another model (Codex), by my delegation. It read the code; it did not run the patches. I checked
  its calls on the two tasks that hold 8 of the 11 "worse"; the other 3 I did not review.
- The team is one way to build a team, with my prompts. The setups differ in how the work is split **and** in how the
  review runs (A reviews in its own session, B calls a fresh reviewer subagent); `agent/agent.py`'s docstring says
  only the first.
- I made the validator stricter after the runs (E22) and re-checked all 32 attempts: 31 kept their verdict. One
  single-agent fix (T1, repetition 2) fell, because one of its 3 samples was cut by the per-file time limit before
  reporting any case. It counts again only because of a rule I wrote after seeing it (E23: a cut before any case is not
  a verdict, and the validation is redone once), on a redo with less load on the machine. Without that rule, one agent has
  6 fixes, not 7 (`report/collection/revalidate-c1.log`, `e23-c1.log`).
- During repetition 1 the provider account ran out of credit (08:27 UTC); the 10 attempts it cut were voided and re-run
  after a top-up (E20; `report/collection/voided-c1.meta.jsonl`).
- Repetition 3 did not run: the budget rule set before the first run stopped it (US$ 3.89 left, US$ 6.57 needed).
- `report/c1-context-per-run.csv` covers 26 of the 32 attempts: the gateway's per-call log of the first hour was lost
  in pod restarts. Per-run totals for all of them are in `gateway-budget.json`.
- The app's code isn't public, so these exact tasks can't be re-run.
