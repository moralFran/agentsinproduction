# Experiment 04 · cluster integration, follow-up round (2026-11-12, same VM restarted)

Second run on the cluster, for the follow-up hardening of the harness. First round: `../integration-2026-11-12/` (harness 1160dcd).
**Nothing here is a re-classification**, the archive was only read, and the live agent attempts in `attempts/` are **integration checks, not data**.

## Read this first

- **The harness needed one change to run on the cluster, applied only in the VM's fresh-run folder** (`harness-fix/executor-safe-directory.diff`,
  one argument added to `checker_git` in `executor/executor.py`). Without it every integrity check fails: see "Defect" below. No file in either
  repository was changed. Every reproduction and validation result of this round was produced with that patched executor.
- **Which commit ran what.** The brief changed three times while the VM was up. Started from the public copy at `dec7c18` (`git archive`), then
  files copied over from `e7858e9` (agent, executor, attempt.sh), `cdffecd` (gateway, attempt.sh) and `d5e1195` (agent, attempt.sh, analyze.py,
  queue.py), each time from the commit, not from the working tree. sha256 of every file at each step: `setup/05`, `06`, `07`.
  The final state equals commit `d5e1195` plus the VM-only fix. What ran on which state:

  | What | Harness state when it ran |
  |---|---|
  | Preparation of all 11 cases | `prep.py`, `prep_worker.py` of dec7c18 (unchanged in the later commits) |
  | First smoke reproduction (gobwas/ws, scrapy-redis, QuantDinger), 20:56Z: all `infra_error` | executor e7858e9, **unpatched** |
  | Every reproduction that counts, every validation, the validator controls, the freeze gate | `repro.sh`, `pod.py`, `validate.py`, `freeze.py` of dec7c18; executor e7858e9 **+ VM-only fix** |
  | Gateway admin and token controls | run twice: on the dec7c18 gateway (20:57Z) and on the cdffecd gateway (21:02Z); identical |
  | Agent environment probe (`RUN_TOKEN`) | run twice: agent.py of e7858e9 (21:06Z) and of d5e1195 (21:44Z); identical |
  | Gateway-unavailable check and the two live smoke attempts | agent.py and attempt.sh of d5e1195, gateway of cdffecd (the same file in d5e1195) |

  Nothing was reproduced or validated with the dec7c18 executor (the e7858e9 files arrived before the first pod), so there is no
  `dec7c18/` subfolder and no before/after of the `.gitignore` fingerprint from this run.

## Answers to the questions

VM on from 20:51:50Z to 23:52:48Z (3.02 h). Model spend of this round US$0.1946 (21 requests, two live attempts); gateway `halted: null` at the end.
All reproduction and validation numbers below come from the executor of e7858e9 **with the VM-only fix**.

1. **Does any real suite now get `test_changed_tree`? No.** Maintainer controls: `integrity_control` clean in 11 of 11 cases (3 suite samples each,
   plus 3 hidden samples in the 9 cases with hidden tests), and `cache_control.integrity` clean in the 7 Go cases (3 + 3 samples each). Archived
   patches: 0 of 56 attempts (36 distinct patches, 174 validation pods) ended `test_changed_tree`; none ended `infra_error` or `timeout`.
   The index refresh works with the box's Git 2.39.5 once Git accepts the checkout (see the defect).
2. **Does the maintainer's fix pass with the agent's cache, and does the broken tree compile? Yes, in all 7 Go cases.** `cache_control`:
   applicable, passes true, integrity clean, suite 3/3 and hidden 3/3 for gobwas/ws, mcp-go, scc, cosign, minify, yarr and miniredis;
   not applicable for the 4 Python cases. `prep_control.broken_compiles` is true for the 7 Go cases (null for Python). `repro-compare.md`.
3. **Do the hidden phases give the same outcomes with the broken-tree cache? Yes.** All 56 attempts have the same outcome and the same suite and
   hidden pass counts as in the first round (0 differences); against the archive 50 are the same and 6 differ, the same six nkanaev/yarr attempts
   as before (`green_no_hidden_tests` → `green_fails_hidden`, 3/3 and 0/3, because the case now has hidden tests). Main analysis recomputed:
   48 attempts, 30 green, 4 failing the hidden tests (all gobwas/ws), v1 15, v2 15: unchanged. `revalidation.md`.
4. **Does token auth work live? Yes.** Two live attempts authenticated with their tokens (scrapy-redis: 9 model calls, US$0.0706, `ci_still_red`;
   gobwas/ws: 12 calls, US$0.1240, `green_fails_hidden` 3/3 and 0/3). While the gobwas run was open, a request with only its `x-run-id` got 403.
   Control run from the host, no model call: no credential 403; only `x-run-id` 403; the run id as token 403; a wrong token 403; the run's token
   accepted (the request then fails on purpose with 400 `max_tokens is not a number`, after the token check); the same token after close 403;
   reuse of the run id 409. The token string is absent from the gateway log and state file (which holds its SHA-256), from admin GET replies
   (keys: calls, cap_usd, open, opened, spent_usd) and, for the live attempts, from the attempt journal, the patch and the agent pod log:
   searched by hashing every 43-character candidate against the stored `token_hash`, 0 matches. The admin controls of the first round
   (401 without the admin key, 400 for the invalid caps) hold on both gateway versions. `gateway/`, `attempts/smoke-attempts.log`.
5. **Does the `.gitignore` fingerprint turn any maintainer control or archived patch into `test_changed_tree`? No, none** (same counts as in
   answer 1; there is no `why` to report). There is no before/after against dec7c18: nothing ran with that executor.
6. **Is `RUN_TOKEN` absent from the tool's environment, and do attempts still authenticate? Yes.** In a pod of the agent's shape that loads
   the harness's own `agent.py` with a dummy token and calls its `bash()` tool function: 0 variables named `RUN_TOKEN` in the tool's environment
   and 0 occurrences of the dummy value, with agent.py of e7858e9 and of d5e1195. As the code comment says, the variable is still in
   `/proc/<agent pid>/environ`, which a tool command of the same uid can read (the probe found it there). The two live attempts used agent.py of
   d5e1195 and authenticated; none of their recorded commands mentions the token or reads the environment (`env`, `printenv`, `environ`). `network/probe-agent-env*.log`.

Also checked, as asked in the updates:
- **SDK in the box image** (anthropic 2.8.0, agent venv, no model call): `APIStatusError.__init__` sets `self.status_code = response.status_code`;
  instances of `RateLimitError`, `PermissionDeniedError`, `InternalServerError` and `APIStatusError` built with a stand-in response carry
  429, 403, 503, 529; `APIConnectionError` exists and is not an `APIStatusError`; `APITimeoutError` is its subclass; `RateLimitError` is a
  subclass of `APIStatusError`. The image has no `httpx` module (the SDK imports `httpx2`). `setup/07-d5e1195-files-and-sdk.log`.
- **`gateway_unavailable` path, live and without spending:** the unmodified `attempt.sh` was started for a smoke round and its run closed from
  the host before the agent pod started. Twice: the agent got 403, reported `gateway_unavailable` with 0 model calls and no patch; `attempt.sh`
  exited 1, wrote one line per try to `smoke/infra-smoke-gwdown.jsonl`, wrote no journal and left no patch file; the second invocation opened
  `…-r1-t2`. Nothing was booked by the gateway. `attempts/gateway-unavailable-check.log`.
- **Freeze gate:** with an empty decisions file `freeze.py` stopped with `case boyter-scc-4288f7c8 needs an eligibility decision in
  cases/eligibility-decisions.json (the hidden control does not discriminate): include/exclude, reason, reviewer, repro_sha256=c331096a…bd0b`;
  a decision with a stale digest got the same refusal; with the right digest it moved on to nkanaev/yarr (same reason); with throwaway
  decisions (scc include, yarr exclude; reviewer "integration check, not a real eligibility decision") it froze 10 cases and listed yarr as
  `excluded_after_eligibility_review`. No Go case needed a decision for compilation or the cache control. `freeze/freeze-gate-check.log`.
- **Validator controls:** the same three patches as in the first round (byte-identical): test file and `.github/workflows/x.yml`
  `rejected_by_validator`; the probe patch `green_fails_hidden` with `not readable` for all four paths in all six samples.
- **Mounts and cleanup:** the fixed-tree Go cache is mounted only in `repro fixed`; `repro fixed-agent-cache` gets `fix.diff` and `hidden.diff`
  but not that cache; validation test containers get neither diffs nor the fixed cache in either phase. At the end no harness pod and no
  `*-patch` ConfigMap was left. `network-controls.md`, `setup/08-final-state.txt`.
- **Network policies:** same behaviour as in the first round, including its weakness: the policy applies some tenths of a second after a pod
  starts (7 of 8 timed pods without an init container), and single connections get through later (a validation test container reached
  the node's ssh port in its first try in 2 of 2 pods and the gateway's model port once at 10.9 s; a preparation pod reached the Kubernetes
  API ClusterIP at 11.9 s). `network-controls.md`.

What had to be worked around: (a) the executor defect below; (b) after the restart k3s registered a second node under the short host name,
without the Kata labels; restarting k3s once the host name was complete and deleting the stray node object restored the original node
(`setup/01`, `02`); (c) the scrapy-redis case has no green archived patch, so QuantDinger was added to the smoke to cover a Python patch that
reaches the hidden phase; (d) the full set was started when preparation, reproduction, validation, probes, token controls and the first live
attempt were clean, while the second live attempt (gobwas/ws) was still running.

Not verified: a state-write failure of the gateway (not provoked, as instructed); a complete round through `run-round.sh`; the 113-candidate
pipeline; `analyze.py` and `queue.py` of d5e1195 (copied, not run); the outcomes `test_changed_tree`, flaky and `did_not_apply` on a real case
(none occurred); a Go case whose broken tree does not compile or whose fix fails with the agent's cache (none among the 11); the working-tree
state of the public copy after d5e1195, if any.

## Defect found: the new integrity checker cannot run in the pods

`executor.py` (since dec7c18) runs the integrity checker's Git commands through `checker_git`, which sets `GIT_CONFIG_NOSYSTEM=1` and
`GIT_CONFIG_GLOBAL=/dev/null`. The box image carries `safe.directory = *` in the **system** Git configuration (`infra/Dockerfile.box`), and it
needs it: the working copy is an `emptyDir` owned by root while the tests run as uid 1000. With the system configuration switched off, Git
2.39.5 in the image refuses the checkout ("detected dubious ownership"), `git status` fails, and every sample comes back as
`infra_error: cannot verify test-tree integrity: git status failed`. In the first smoke all three cases (gobwas/ws, scrapy-redis, QuantDinger)
ended `infra_error` with fixed 0/3 and an integrity control of `error` (`repro/repro-before-fix.jsonl`, `pod-logs-before-fix/`); the same would
happen to every validation. The local tests cannot see it: on the Mac the checkout belongs to the user who runs Git.

Fix used here, in the VM's fresh-run folder only: one more `-c safe.directory=*` in `checker_git` (command-scope configuration is protected
configuration, so Git honours it). Diff: `harness-fix/executor-safe-directory.diff`. sha256 of the patched `executor.py`:
`0a16040ead580738851b015d79c909f9f9347cc839601818c1dd0f885e49618a` (e7858e9/d5e1195 original: `4904dadb…7b90`). It is not applied in
either repository.

## What is in this folder

Same layout as the first round: `setup/` (restart, node-name workaround, new fresh-run folder, setup-lab, file updates and hashes, SDK
introspection), `prep/`, `repro/` (`repro.jsonl`, `prep.jsonl`, `repro-before-fix.jsonl`), `repro-compare.md`, `freeze/`, `network/`,
`gateway/`, `smoke/`, `attempts/`, `revalidation/` + `revalidation.csv` / `revalidation.md`, `validator-controls/`, `pod-logs/`
(`pod-logs-before-fix/` for the failed first smoke), `harness-fix/`, `controls/` (the scripts of this round; not part of the harness).
User name, external address and project id are replaced by `<user>`, `<external-ip>`, `<project>`.
