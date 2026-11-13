# Changes for future runs · 2026-11-12

This addendum was written **after** collection, auditing and judging. It describes the current harness, not the one
that produced the archived 66 attempts. `criteria.md` remains the dated historical protocol. A new collection must
record its harness revision and these changes before starting; its outcomes are not an exact replay of the archive.

## Preparation and inputs

`cases/prep.py` is now a trusted host controller: it fetches the repository, creates a single-commit snapshot and
stores reference diffs under `/srv/ci/secret/<case>`. It does not install dependencies or run repository code.
`cases/prep_worker.py` performs those operations inside a disposable Kata pod in `ci-prep`. Each worker receives
one read-only snapshot and one writable output directory. It has no mount for the lab checkout, the secret directory,
credentials or another case. Preparation runs as the non-root lab user UID/GID so the host owns its output;
agent/executor pods retain UID 1000. Source symlinks escaping the checkout and symlink output roots are rejected.

The broken-tree Go cache is the only cache published to the agent. A separate fixed-tree worker starts with a copy
of that cache and writes to a private output; its dependencies are available only to the maintainer's fixed-tree
reproduction control. Both agent validation phases (original and hidden) use the broken-tree cache, as does the
broken-plus-tests control. Validation does not silently substitute the fixed-tree cache, so the two arms of the hidden
control differ in dependencies as well as in code: if the hidden tests need a module the broken-tree cache lacks,
broken-plus-tests fails for that reason, the control looks discriminating, and every green agent patch would be
classed `green_fails_hidden` by rule. Reproduction therefore runs a fourth control for Go cases, `repro
fixed-agent-cache`: the maintainer's fix, original suite and hidden tests, three samples each, with the broken-tree
cache (the environment agent patches are validated in). It runs only when the broken tree failed 3/3 and the fix
passed 3/3. The result is `cache_control` in the reproduction record. Passing requires exit code 0 **and** an unchanged
tree in every sample, the same integrity rule validation applies: with this cache a command can end 0 and still write
`go.sum`, and validation would then record `test_changed_tree` for every agent patch. The record keeps each sample's
integrity result and the reason (`integrity: changed`, `why`). A missing, incomplete or timed-out control, or one whose
integrity check did not run, is an infrastructure error. A control that fails does not change the verdict:
`freeze.py` requires an eligibility decision, and its message says whether the fix failed or changed the tree.
Python runtimes are also per case. Prepared caches and build products remain untrusted repository output: the host
copies them without executing them, and execution stays in the sandbox.

On the maintainer's **fixed tree**, the selected Go packages must compile and start successfully with
`go test -count=1 -run '^$' <targets>` before `PREP_WORKER_DONE`. A failed bulk `go mod download` can be optional (it
may include unused modules), but is logged as `PREP_OPTIONAL_FAILED`; the subsequent compile is mandatory there.
Python's runtime and pytest installation are mandatory; optional dependency groups remain best-effort. A required
preparation failure stops that worker and is recorded as preparation failure, rather than allowing a later test
failure to masquerade as a non-reproducing case.

On the **broken tree** the same compile runs but is not fatal: a build can be red precisely because it does not
compile, and making the compile mandatory there would silently drop that kind of failure from the case set. The
worker prints `PREP_COMPILE {"phase": "broken", "ok": ...}`; the controller keeps the last such line as
`broken_compiles` in the case's public metadata and in `prep.jsonl` (it says nothing about the fix), and reproduction
copies it to `prep_control`. When it is false, `freeze.py` requires an eligibility decision: someone reads the failure
and records whether it is the commit's own error or a module missing from the sandbox.

Preparation permits DNS and public HTTP(S) downloads, with private and link-local address ranges excluded. These
policies require a working CNI implementation. Kubernetes exempts traffic to/from a pod's own node, so they are not a
host firewall; verify the actual runtime/network behavior before collecting. See the
[Kubernetes NetworkPolicy documentation](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Use a fresh VM and run `infra/install-docker.sh` (Docker for image builds, plus host Git/rsync), then the remaining
README setup steps. The old globally shared preparation directories are not reused. `cases/pipeline.sh` processes
all available candidates and exits when none remain unclaimed; it no longer stops at 30 reproductions or waits forever
on an empty queue. Wait for **every worker** to finish before retrying infrastructure failures or freezing the list.

## Validation and hidden-test controls

`cases/validate.py` launches **three fresh pods** for the original suite. Only after all three pass does it launch
three more fresh pods for the hidden suite, when present. In each pod an init container copies the snapshot, checks
and applies the agent patch, and applies the hidden diff if needed, without running case code. The test container
receives that prepared tree and a read-only preparation record. It mounts **no input diffs or secret metadata**.
`fix.diff` is mounted only for the maintainer reproduction control, never for agent validation.

Each sample compares Git status and tracked/non-ignored file content before and after execution, so another edit to
an already modified file is detected. The checker retains the pre-test file inventory and fingerprints `.git/config`,
`.git/info/exclude`, `.git/index`, `.git/HEAD` and the type of `.git` itself. It does not consult Git again if these
metadata change. Git checks disable fsmonitor, hooks and untracked caching, remove inherited Git overrides and ignore
global/system configuration. `GIT_OPTIONAL_LOCKS=0` avoids Git status refreshing the index itself; see the
[Git environment reference](https://git-scm.com/docs/git#Documentation/git.txt-GITOPTIONALLOCKS).
Because `.git/index` is fingerprinted, the checker refreshes the index once before taking its baseline: the checkout
is a copy, its index holds stale stat data, and without the refresh a suite that merely runs `git status`, `git diff`
or `git describe --dirty` would rewrite the index and be recorded as `test_changed_tree`. The checker also pins
`core.excludesFile` to `/dev/null`; Git otherwise reads `$HOME/.config/git/ignore`, and `HOME` is writable in the pods,
so a test could hide new files from the listing. Both were found in review and reproduced on a synthetic repository
before the fix; neither has run against a real suite yet.
Git's listing also honours `.gitignore` files in any directory, so a test could create `new/.gitignore` containing `*`
and hide everything in `new/`, the ignore file included. The checker therefore finds every `.gitignore` by walking
the checkout on disk and fingerprints them in both states: a new or edited ignore file is itself a change. The cost
is that a suite whose tools create self-ignoring cache directories (a `.gitignore` with `*` inside the directory, as
several linters and coverage reporters do) is now recorded as `test_changed_tree`; on the maintainer control that
makes the case `incompatible_test_side_effects`. Whether any real case is affected is a question for the cluster run.
`executor.py repro` rejects an unknown tree name instead of running the command in an empty directory.
During reproduction, the maintainer's fix now undergoes this **same integrity
check**, for all original and hidden samples. Each sample starts from a restored snapshot with the fix reapplied;
restoration checks file content, so same-size edits within one timestamp tick cannot survive. If the fixed suite
itself leaves unignored reports, coverage files or other changes, an otherwise reproduced case is recorded as
`incompatible_test_side_effects`, with the phase and reason in `integrity_control`. It is excluded before freezing,
not counted as a rejected agent patch. Missing/failed integrity checks are infrastructure errors, and `freeze.py`
refuses any reproduced case without a clean control, including records from the earlier harness.

For eligible cases, persistent tree changes produce `test_changed_tree`, distinct from `rejected_by_validator`
(forbidden patch paths or unreadable path information). Original-suite mixed results become
`ci_flaky_after_patch`; hidden mixed results become `hidden_tests_flaky`, not automatically `worse`. Only three hidden
failures produce `green_fails_hidden`; three passes produce `green_passes_hidden`. Missing results and timeouts are
infrastructure/timeout outcomes. Each validation sample starts in a new pod from the snapshot.

A green attempt with hidden tests starts up to six Kata validation pods. If both original and hidden commands take
about 140 seconds (the order of the archived ludwig original suite), that is 6 × 140 = 840 seconds, or 14 minutes,
plus pod startup and preparation: allow roughly 15 minutes per attempt just for validation. This is an estimate,
not a measured runtime of the new harness; VM time and capacity should be budgeted separately from model calls.

Reproduction now records three hidden runs on the maintainer's fix and three on **broken code plus only the test
changes**. Missing/timed-out samples prevent reproduction; mixed hidden results are intermittent; a consistently
failing hidden suite on the fix prevents inclusion. `hidden_control.discriminates` reports whether all fixed runs
pass and all broken-plus-tests runs fail. The broken and broken-plus-tests checkout is now restored before every
sample, with the test diff reapplied for the latter; the fixed control also restores and reapplies the fix each time.
Reproduction still groups samples in one pod per control, so `/tmp`, background processes and other state outside
the checkout are not reset between its samples. It does not provide validation's per-sample pod isolation.

Before freezing, three conditions now require an explicit decision, and the message of `freeze.py` names which:
an applicable but non-discriminating hidden control (tests may themselves be the fix); a Go case whose broken tree did
not compile in preparation; a Go case whose maintainer fix does not pass with the agent's dependency cache.
`freeze.py` stops until `cases/eligibility-decisions.json` contains an entry such as:

```json
{
  "example-case-id": {
    "decision": "include",
    "reason": "Explain the relation to the original failure and why this case remains eligible.",
    "reviewer": "reviewer name",
    "repro_sha256": "exact digest printed by freeze.py"
  }
}
```

Both `include` and `exclude` require a non-empty reason and reviewer. The digest binds the decision to the current
reproduction record (SHA-256 of sorted, compact JSON), so rerunning reproduction requires a fresh decision. A successful
freeze copies the applied decisions to `cases/eligibility-at-freeze.json`; explicit exclusions appear in
`cases/not-reproduced.csv` (verdict `excluded_after_eligibility_review`) and the funnel. Fresh runs start with an
empty decision file. A case with none of the three conditions needs no decision. Earlier records without an explicit
hidden-control applicability result, and Go records without `prep_control` or `cache_control`, must be prepared and
reproduced again: `freeze.py` refuses them.
Even a true value does not prove that every hidden assertion concerns the original failure; inspect that relationship
as well. These controls do not replace the rule-9 review illustrated by QuantDinger, scc and yarr.

The archived hidden check ran once, with later audit reruns for failures. It was **not retroactively changed** to this
three-sample rule, and no archived outcome was recomputed with new tests.

## Remaining trust boundary

This is not an adversarially sound proof of correctness. Applied test files must be readable by the test process;
repository code can tamper with its own runner, exit before assertions, modify ignored files, or change and restore
files between snapshots. The integrity checker still runs under the test process's UID, so in-process interference
and background races remain possible; protecting Git metadata does not make that boundary adversarially sound.
The same-UID agent loop/result channel is also not a security boundary. Choosing the last
`RESULT` and disabling Git external diff/textconv reduce accidental/spoofed output paths, but do not solve that class.

`infra/test_security.py` contains a deliberate negative control: production code executes `os._exit(0)` when imported
by a script whose next assertion always fails. The command reports success and leaves the tree unchanged. The test
**expects this bypass**, documenting why every green patch still needs semantic review. Do not count that negative
control as evidence that bypassing the runner has been prevented.

The path validator also rejects `.pytest.ini`, `pytest.toml` and `.pytest.toml`, alongside `pytest.ini` and the existing
configuration names. TOML configuration was introduced in pytest 9; see the
[pytest configuration reference](https://docs.pytest.org/en/9.0.x/reference/customize.html).

## Gateway, runner and judging

The gateway requires a separate bearer token for **all** admin requests. `infra/setup-lab.sh` creates a random token
at `/srv/ci/admin-key` (0600) and in the `gateway-admin-key` Secret; only the gateway mounts it. `attempt.sh` reads the
host copy and sends it via curl's stdin configuration, not a process argument. An ingress policy allows model traffic
from `ci-agent` on 8080; the host runner uses 8081 with authentication. Do not copy this key into case inputs or logs.

Opening a run also returns a **separate random 256-bit model token**, exactly once. The runner passes it through the
pod environment; the agent sends `x-run-token`. Public run ids remain log labels and cannot authorize requests, even
while other attempts are open. The gateway stores only token hashes, rebuilds the lookup on restart and revokes the
token on close. Admin reads, close responses, gateway logs and upstream headers omit it. The agent harness removes
the token from its environment as soon as it has read it, so the bash tool and the repository code it runs (tests,
build scripts) do not inherit it. That is not a boundary: a process of the same UID can still read the harness's
initial environment in `/proc/<pid>/environ`. What bounds a leaked token is the run's cap, one model, and revocation
at close. The agent receives no provider or admin key. If a run opens but the reply carries no usable token,
`attempt.sh` closes the run before giving up. Existing tokenless runs cannot authenticate after this change;
they are not reset or reopened automatically. Preserve their recorded costs and start future collections separately.

The open check and reservation now share the same lock as administrative closure. Closing before reservation rejects
the call; calls already reserved may still complete and be billed to that run.

A close that cannot be written to the state file used to leave the run closed in memory and open on disk, so a restart
would have accepted its token again. Now the gateway answers 503, keeps the run closed and the token revoked in that
process, and halts: nothing is forwarded for any run until a close is written, and that write carries every closure
made in memory. `attempt.sh` retries the close three times; if the gateway never confirms, the attempt is recorded
with unknown cost and the script fails, which stops the round. One limit remains and is shown by a test on purpose:
while the state cannot be written a revocation cannot be made durable, so a restart before the close is written brings
the token back. Make the state writable and close the run again before restarting the gateway. Setup explicitly restarts the gateway
deployment after updating its ConfigMap and waits for rollout completion, so the next run uses the new Python process.

Run caps must be finite, positive and no greater than `MAX_RUN_USD` (default US$ 0.33). Changing that upper limit is an
explicit new-run configuration decision; the total budget remains a second bound. Upstream redirects are not followed.
Both listeners limit active connections (default 32 each) and idle reads/writes (default 15 seconds). This bounds
resource use but does not guarantee availability against sustained denial of service.

Both the agent's shell and the round runner use `pipefail`. After a round, `cases/check-round.py <round>` requires
exactly one record per frozen case/repetition and unique run ids. On the historical set that is 33 per version.
Re-running `run-round.sh` skips attempts already in the JSONL journal, including recorded failures, with exit status
zero and without accessing the prepared tree, opening a gateway run or rewriting a patch. Malformed journals and
failures of pending attempts still stop the round. This resumes completed journal entries; it does not automatically
reconcile a gateway run opened before a crash that produced no attempt record.

**An infrastructure failure of the model path is not an attempt.** Three attempts run at a time, so when the gateway
halts (a close it could not write, a call above its reservation) or the provider fails, the attempts in flight get
errors that are not theirs. Before, the agent treated only its own cap (429) specially: a 503 became `error`, whatever
was half-edited in the working copy was validated, the result entered the journal, and the resume then skipped it. Now
the agent harness classifies a failed model call by its HTTP status: 429 naming this run's budget is
`budget_exhausted`, an outcome of the attempt; a 5xx or 529, a 403 from the gateway, any other 429 (total budget,
provider rate limit) or a lost connection is `gateway_unavailable`, and the harness returns no patch. `attempt.sh`
validates nothing for such a try and does not write it to the journal: it goes to `results/infra-<round>.jsonl` with
the reason, what the agent reported and what the gateway booked, and the script fails, which stops the round after the
repetition in progress. On resume the case/repetition is redone under a new run id (`-t2`, `-t3`), because the gateway
refuses a reused id; the same now applies to a run that opened without a usable token. After three such tries for the
same case and repetition the script refuses to continue until someone looks. A 400 from the provider (for example a
conversation that grew too long) stays an `error` of the attempt. Two things to keep in mind: the classification is
reported by the agent's pod, like the rest of its result; and what those tries cost is in the infra file and in the
gateway's totals, not in the tally, whose total is already labelled a lower bound.
The tally handles apply failures, validator rejections, flaky tests, missing output and infrastructure failures without
requiring a blind key. A no-patch timeout/tool-limit/error is no longer called a voluntary give-up. Unknown cost remains
unknown and the total is labelled as a lower bound.
The cost-table label derives attempt counts from each round; unequal round sizes are displayed separately.

The judge accepts verdict writes only as `application/json` with a matching local Origin when supplied; browser
cross-origin and `text/plain` requests are rejected. Non-browser clients may omit Origin. Existing append-only verdict
files and the archive guards are unchanged.

## Verification of the earlier hardening (baseline `ecdbcd7`)

- `python3 -B executor/test_executor.py`: 31 checks on synthetic patches.
- `python3 -B infra/test_security.py`: 22 tests, including six independent sample processes with preparation/run
  separation, mount contracts, persistent tree mutation, cache separation, hidden-control completeness, actual shell
  failure propagation, empty-queue exit, tally categories and judge request checks. The follow-up regressions exercise
  actual shell round resumption and executor → reproduction → freeze, including original/hidden suite-generated output,
  a clean control and refusal to freeze records without the new integrity control.
- `python3 -B infra/test_workflow.py`: 8 tests of new-run setup, funnel, tally and audit resumption.
- `python3 -B gateway/test_budget.py --short`: 17 checks against a local fake upstream, including admin authentication,
  invalid caps, redirects and slow partial requests; no provider call.

These checks exercise local behavior and generated manifests. **Kubernetes/Kata startup, CNI enforcement and the
third-party suites were not run for this patch.** Those remain the integration checks for the next lab session.
The 66 attempts, their patches, frozen cases, blind packets/verdicts and audit logs remain byte-for-byte unchanged.
Regenerating the historical final tally and funnel in a temporary copy yields identical output.

## Independent re-test of the baseline patch (2026-11-12, `ecdbcd7`)

A second pass re-ran everything above from a clean checkout of this folder, without a cluster:

| Check | Result |
|---|---|
| `python3 -B executor/test_executor.py` | 31/31 |
| `python3 -B infra/test_security.py` | 22 tests, OK |
| `python3 -B infra/test_workflow.py` | 8 tests, OK |
| `python3 -B gateway/test_budget.py --short` | 17 checks, 0 failed |
| `bash -n` on every script in `cases/` and `infra/`; `py_compile` on the Python sources | clean |
| `results/analyze.py` and `cases/funnel.py` re-run in a temporary copy | `final-summary.md`, `final.json` and `funnel.md` byte-identical to the archive |
| Archived records (`results/attempts-*`, `patches/`, `blind/`, `cases.csv`, `repro.jsonl`, `criteria.md`) | unchanged; only the script `results/analyze.py` differs |

Two defects found in that pass were fixed before this commit, each with a regression test:
1. **An interrupted round could not be resumed.** `run-round.sh` now stops on any failing attempt, and `attempt.sh`
   used to exit 1 for an attempt that was already recorded, so a second invocation failed in repetition 1 and never
   reached the rest. A recorded attempt is now skipped with exit 0 (the journal is parsed, not grepped).
2. **The tree-integrity check could reject every patch of a case whose suite writes files into the tree** (coverage
   output, generated files). Reproduction now runs the same check on the maintainer's fix; a suite that changes the tree
   gives the verdict `incompatible_test_side_effects`, and `freeze.py` refuses a case without a clean control.

**Still open: the cluster integration.** Pod start under Kata with the init container and the shared working tree, the
per-case preparation pods running as the VM user, seccomp, the nested read-only mounts and the three NetworkPolicies
have only been exercised locally with stand-ins. The planned check, on a fresh VM, is: build the lab from an empty
machine; prepare and reproduce the 11 frozen cases with the new preparation; re-validate the 56 non-empty archived
patches with the new validator and compare each outcome with the archived one; run the gateway admin, cap and ingress
controls live. That run happened on 2026-11-12: see "Cluster integration" below. The archived results stand on the harness
that produced them.

## Follow-up verification (2026-11-12, after the baseline re-test)

All checks below passed locally on the follow-up implementation:

| Check | Result |
|---|---|
| `python3 -B executor/test_executor.py` | 31/31 |
| `python3 -B infra/test_security.py` | 41 tests, OK |
| `python3 -B infra/test_workflow.py` | 9 tests, OK |
| `python3 -B gateway/test_budget.py --short` | 22 checks, 0 failed |

New regressions exercise token-bound parallel budgets, restart/revocation and closure between lookup and reservation;
a close that cannot be written (revoked in memory, forwarding halted, durable once written, and the restart limit);
model-path failures classified by status and returned without a patch, kept out of the journal and redone under a new run id;
Git metadata tampering without executing fsmonitor; retained pre-test file inventories; suites that only query Git;
an ignore file planted in `HOME`; a new self-ignoring directory; the token absent from the tool's environment;
a run closed when its token cannot be read; an unknown reproduction tree; Go compilation, mandatory on the fixed tree and recorded on the broken one;
the maintainer's fix under the agent's dependency cache, from the executor through `repro.sh` to `freeze.py`,
including a command that ends 0 but writes `go.sum` only under that cache;
checkout restoration on broken/hidden reproduction; eligibility decisions and stale digests; gateway rollout ordering;
and the tally's actual round sizes and distinct tree-mutation outcome. Local servers use a fake upstream and make no
provider calls. The earlier re-test record above is retained with its original counts.

The cluster check planned here (one Go and one Python case first, then the 11 historical cases and the 56 non-empty
archived patches, results written separately from the archive) was run afterwards: see "Cluster integration, follow-up
round" below. It found one defect that no local test could show.

## Cluster integration (2026-11-12, fresh VM)

> Read with the section "Network investigation and review changes (2026-11-13)" at the end: the start-up window was
> measured again there (it is not limited to 0.3 to 0.7 s), and the single late connections reported in this section and
> the next were found to be a probe artifact in the Kata guest, not connections.

First run of the hardened harness on a real cluster. **Revision tested: the first hardening of 2026-11-12** (the sections up to
"Independent re-test", commit `ecdbcd7`), not the follow-up above, which was written while this run was in progress and ran on the
cluster afterwards (next section).
Everything is in `results/integration-2026-11-12/` (README with the answers, raw logs, tables, and the probe scripts in `controls/`).
No archived record was written; the archived outcomes stand on the harness that produced them.

**What was run.** A new VM (n2-standard-8, k3s v1.37.2+k3s1, Kata 4.3.1, on for 3.27 h) built with `infra/create.sh`,
`install-docker.sh`, `install-k3s-kata.sh`, `build-images.sh` and `setup-lab.sh`; a fresh run folder from `infra/new-run.sh
--with-candidates`, its candidate files reduced to the 11 frozen records; three `cases/pipeline.sh` workers; `cases/freeze.py`;
`cases/validate.py` on the 56 non-empty archived patches (36 distinct); probe pods built with `pod.py` and `prep.py`'s own spec builders;
the gateway admin controls from the host; three validator control patches; two agent attempts on gobwas/ws (an integration check, not data).

**What passed.**
- The lab came up from an empty machine in six minutes with the current scripts. No harness script failed.
- Preparation pods ran under Kata as the lab user with only their own input and output; validation pods ran the init container and the
  test container had no input diff and no secret directory. The fixed-tree Go cache was mounted only in fixed and hidden pods.
- The 11 frozen cases prepared and reproduced (11 of 11, integrity control clean). `freeze.py` froze 11 on the fresh run.
- 56 of 56 archived patches re-validated: 50 with the archived outcome. The main-analysis numbers computed from the new validator's
  outcomes are the published ones (48 attempts, 30 green, 4 failing the hidden tests, all gobwas/ws; v1 15, v2 15).
- A test-file patch and a `.github/workflows/x.yml` patch were `rejected_by_validator`. A patch that tries to read `/in/hidden.diff`,
  `/in/fix.diff`, `/in/patch.diff` and the case's secret `meta.json` from inside the tests found none of them readable, in six of six samples.
- Gateway: 401 on the admin port without the token or with a wrong one; caps above `MAX_RUN_USD`, non-finite, zero, negative or missing
  refused with 400; runs opened and closed with the token. Agent pods reached the model port; pods of other namespaces did not.
- The round runner stopped at the first failing attempt (`pipefail`, exit 123); a recorded attempt was skipped without spending;
  `check-round.py` rejected two one-attempt rounds and accepted the archived rounds. Model cost US$0.2447, 20 requests.

**What differed or failed.**
1. **nkanaev/yarr now has hidden tests.** `prep.py` treats `fixtures/` as test data, so the fresh `cases.csv` differs from the archive in
   that row, and the six yarr patches go from `green_no_hidden_tests` to `green_fails_hidden` (suite 3/3, hidden 0/3). yarr is outside the
   main analysis (amendment 24). These six are the only outcome differences.
2. **`hidden_control.discriminates` is false for boyter/scc and nkanaev/yarr**: the hidden tests pass on broken code plus only the test
   changes. Both were already outside the main analysis for that reason. It is true for the seven other cases with hidden tests,
   QuantDinger included, which confirms the warning above that a true value does not prove relevance.
3. **NetworkPolicy does not apply during the first moments of a pod.** k3s's controller (kube-router v2.11.1-k3s1) enforces a namespace's
   policy some tenths of a second after the pod's first process starts. In 24 of 31 timed pods without an init container (agent, executor
   repro, preparation) the public internet, the metadata endpoint, the node and the Kubernetes API answered for the first 0.3 to 0.7 s.
   Validation test containers start after the init container and had no window (8 of 8). In those first moments agent pods were also
   refused by the gateway. Reproduction pods (`repro broken`, `fixed`, `hidden-broken`) run case code with no init container before it.
4. **Rare single connections through a policy that was already applied**: one to the Kubernetes API ClusterIP from an executor pod in about
   2,700 steady-state tries, one from a validation test container, one to the gateway's model port from an executor pod and three to its
   admin port (which requires the token) from executor and preparation pods. Cause not investigated.
5. `Seccomp: 0` inside the Kata guest in every pod kind although the pod spec requests `RuntimeDefault` (as in experiment 03).

Findings 3 to 5 come from the cluster software, not from the hardening: the archived collection ran with the same k3s, Kata and policies.

**Bugs found and fixed in the harness: none.** No file under `infra/`, `cases/`, `executor/`, `gateway/`, `agent/` or `k8s/` was changed.
Not fixed, for a future run: gate the start of case code on the policy being in force (an init container in agent and reproduction pods
that waits until a known address is refused, or a CNI that installs policy before the pod's network is usable), and do not describe the
executor as having "no network at all" without that gate. Also seen in the archive: `agent.py` runs commands with `bash -lc`, which resets
`PATH`, so the first `go` command of an attempt returns 127 until the agent exports `/usr/local/go/bin`.

**Still unverified on a cluster.** A complete round through `run-round.sh` and its resume after a real interruption; the pipeline over all
113 candidates; the outcomes `incompatible_test_side_effects`, `ci_flaky_after_patch`, `hidden_tests_flaky`, `did_not_apply` and timeouts on
real cases (none occurred); the gateway's connection limits, idle timeouts, redirect refusal and total-budget halt; and the judge.
The follow-up revision ran in the second round, below.

## Cluster integration, follow-up round (2026-11-12, same VM restarted)

Second run on the cluster, for the follow-up revision described above. **Revision tested: commit `d5e1195` plus one fix made on the
VM**, now in `executor/executor.py` (see the defect below). Everything is in `results/integration-2026-11-12-followup/` (README with the
answers, which commit ran which step with the sha256 of every file, raw logs, tables, the scripts in `controls/`). No archived record
was written. The live attempts are an integration check, not data.

**What was run.** The VM of the first round restarted (cluster and images reused, preparation from scratch in a new fresh-run folder);
a smoke with one Go case (gobwas/ws) and Python cases (scrapy-redis, plus QuantDinger for a patch that reaches the hidden phase):
preparation, reproduction, validation of an archived patch, one live agent attempt each; then the 11 frozen cases, `freeze.py`, and
`cases/validate.py` on the 56 non-empty archived patches (36 distinct, 174 validation pods); the validator control patches and the
gateway admin and token controls.

**Defect found: the new integrity checker could not run in the pods.** `checker_git` disables Git's system and global configuration.
The image carried `safe.directory = *` in the system configuration; the working copy is a root-owned emptyDir and the tests run as
uid 1000, so with that configuration disabled Git refused the checkout ("dubious ownership") and every integrity sample came back
`infra_error: git status failed`. The first smoke ended `infra_error` for all three cases (`repro/repro-before-fix.jsonl`,
`pod-logs-before-fix/`). Fix: `-c safe.directory=*` in `checker_git` (`harness-fix/executor-safe-directory.diff`, applied on the VM
first, then here). The local tests could not see it, because locally the checkout belongs to the user running Git;
`infra/test_security.py` now reproduces it with Git's own different-owner switch. Every result below was produced with the fix.

**Answers.**
1. **`test_changed_tree` on real suites: none.** The maintainer integrity control is clean in 11 of 11 cases and the cache control in
   the 7 Go cases; 0 of 56 archived attempts ended `test_changed_tree`, and none in an infrastructure error or timeout. The index
   fingerprint (after the refresh) and the `.gitignore` fingerprint produced no hit.
2. **The maintainer's fix with the agent's cache, and the broken-tree compile: yes for all 7 Go cases** (`cache_control.passes` true,
   suite 3/3 and hidden 3/3, tree unchanged; `broken_compiles` true). Not applicable to the 4 Python cases.
3. **Hidden phases with the broken-tree cache: same outcomes.** Against the first round, 56 of 56 identical, suite and hidden counts
   included. Against the archive, 50 identical and 6 different, the same six nkanaev/yarr attempts as in the first round. The
   main-analysis numbers computed from these outcomes are the published ones (48 attempts, 30 green, 4 failing the hidden tests, all
   gobwas/ws; v1 15, v2 15).
4. **Run tokens, live: work.** Two live attempts authenticated with their token (scrapy-redis `ci_still_red`, gobwas/ws
   `green_fails_hidden`; US$0.1946, 21 requests). A request with only the `x-run-id` of an open run got 403, a wrong token 403, the
   right token after close 403, a reused run id 409. The token is absent from the gateway log, the state file (hash only), admin
   replies, the attempt journal, the patch and the agent pod's log.
5. **The token in the tool's environment: absent**, checked in a pod of the agent's shape with the harness's own `bash()`. It is
   still readable in `/proc/<pid>/environ`, as documented.
6. **`gateway_unavailable`, live and without model calls:** with the run closed from the host before the pod started, the agent got
   403 and reported `gateway_unavailable` with no patch; `attempt.sh` exited 1, wrote one line to the infra file and none to the
   journal, and the next invocation opened the `-t2` run. Twice.

Also checked: the SDK in the box image (anthropic 2.8.0) sets `status_code` on `APIStatusError`, has `APIConnectionError` with
`APITimeoutError` as a subclass, and `RateLimitError` is an `APIStatusError`, which is what the classification relies on.
`freeze.py` stopped for boyter/scc and then nkanaev/yarr ("the hidden control does not discriminate"), refused a stale digest, and
with throwaway decisions marked as an integration check froze 10 and listed yarr as `excluded_after_eligibility_review`. The
validator controls gave the same three results as in the first round. The fixed-tree Go cache was mounted only in `repro fixed`. No
harness pod or patch ConfigMap was left; the gateway ended with `halted: null`.

**Network: same behaviour and the same start-up weakness as the first round.** New observations: validation test containers reached
the node's ssh port on their first try in 2 of 2 timed pods, and one reached the gateway's model port once at 10.9 s.

**Worked around.** After the restart k3s registered a second node object under the short hostname, without the Kata labels; k3s was
restarted once the hostname was complete and the stray object deleted.

**Still unverified on a cluster.** A gateway state-write failure (covered only by `gateway/test_budget.py` 18 and 19); a complete
round through `run-round.sh`; the pipeline over all 113 candidates; `analyze.py` and `queue.py` of this revision; and real cases that
hit `test_changed_tree`, a flaky outcome, `did_not_apply`, a broken tree that does not compile or a failing cache control: none
occurred among the 11. The `.gitignore` fingerprint has no before/after on real suites, because nothing ran with the earlier executor.

Both rounds: 6.29 h of VM and US$0.4393 of model calls. The VM and its disk were deleted after the second round.

## Network investigation and review changes (2026-11-13, fresh VM, no provider key)

Three external reviews of the two cluster rounds asked what the network findings mean and pointed at four harness
points. This round ran on a new VM for 1.25 h with a dummy gateway key (no model call; the gateway log has no
forwarded request). Full report, scripts and raw data: `results/network-2026-11-13/`.

**Start-up window: reproduced, cause seen at rule level.** A new pod's network works before the policy controller's
next sync has written the pod's chain; until then its packets match no pod rule and are accepted (226 of 226 complete
traces of passed SYNs have no jump into a pod chain). It is not "0.3 to 0.7 s" and not specific to Kata: 0.6 to 0.8 s
for Kata pods on a quiet node, 0.4 to 1.6 s for Kata and 0.1 to 1.1 s for runc pods on a busy one, under 20 ms for
quiet runc pods. 39 of 45 Kata pods and 45 of 45 runc pods without an init container had an established forbidden
connection; 0 of 30 validation test containers (they start after an init container). Nothing bounds the window from
above.

**Late connections through an applied policy: none found; the earlier reports were a probe artifact.** The probe
reported them again, in Kata pods only (76 in 276,318 forbidden tries, with and without churn, internal and external
targets alike). Of the 133 such events in the main block, 126 are shown rejected by a packet of their own (a
time-matched trace line, a single dropped packet, every packet of that address, port and destination dropped, or the
packet capture); 2 are inconclusive and 5 have no trace: those 7 fell in two minutes when no trace reader was
running. None of the 133 has a connection-tracking entry at any time, no packet matched to one was accepted, and
where the socket state was read it was not connected. Inside the Kata guest
`connect()` can return without error for a refused connection (the first `SO_ERROR` reads 0, the next reads 111). Of
928,346 traced SYNs none was accepted outside a start-up window, with 834 controller syncs and 194 pods coming and
going; about 774,000 forbidden tries from long-running pods, none passed. The single late connections recorded on
2026-11-12 cannot be re-examined, but they have the same signature. The re-sync and stale-ipset explanations are not
supported: the first was looked for and not seen, the second could not be tested (no pod address was reused).

**The Kata guest has traffic of its own.** The guest image's time service opens TCP connections to public time
servers (port 4460) from the pod's address as soon as the VM boots: 56 passed before the pod's rules existed, 689
were rejected after. Not case code, and not stopped by the gate below. How to turn it off was not investigated.

**Network gate (new, on by default).** `cases/pod.py` and `cases/prep.py` add an init container, `netgate`, with no
volume and no secret: it tries the forbidden canaries (public address, metadata endpoint, node, Kubernetes API) until
none connects in 8 consecutive rounds over at least 2 s, and for agent pods until the gateway's model port answers;
after 60 s it fails the pod, which is an infrastructure error. With it, 0 of 60 pods had an established forbidden
connection in the main container, against 39 of 60 Kata pods without it in the same minutes. Cost: about 8 s per pod
as configured. `NETGATE=0` builds pods without it. It checks canaries and shows the rules were in force when it
looked; it does not make the policy apply from the pod's first instant and cannot prevent a later lapse. A gate that
fails is an infrastructure error: `attempt.sh` keeps the try in the infra file and redoes it under a new run id
(forced on the cluster: exit 1, no journal row, `-t2` on the rerun). Not run on the cluster: a complete round with it.

**Guest seccomp.** `infra/install-k3s-kata.sh` now sets `disable_guest_seccomp = false` through the chart's drop-in:
`Seccomp: 2` in 8 of 8 new Kata pods, where all pods of the earlier rounds showed 0; the Go case still reproduced
(3/3 and 3/3). First applied to a running lab with `helm upgrade`; then the install script as it is was run on the
same VM after uninstalling k3s and removing `/opt/kata` (not an empty machine): the drop-in was written, and 4 of 4
gated Kata pods showed `Seccomp: 2` and a passing gate. No case code ran after that reinstall.

**Review points changed in the harness** (local tests 46 + 31 + 9 + 24; `criteria.md`, amendment 28):
- `gateway_unavailable` is the pod's own word. The gateway now counts, per run, the model calls that failed for a
  reason the sender cannot cause (`model_path_failures`, with a reason code each: the run was closed, the gateway
  halted or could not write its state, the total cap, an upstream error, a 403/429/5xx from the provider), and
  `attempt.sh` accepts the claim only with that count above zero or when its own close was never confirmed.
  Otherwise the try is an attempt: an error, no patch, not redone. A request the gateway refuses for its own content
  (format, model, size) is never counted, even with a valid token, and the run's cap is checked before the total
  cap, so an oversized request cannot reach the total one (both from a later review the same day). Checked live:
  confirmed claim (not recorded, redone under `-t2`, reason `run_closed`), unconfirmed claim (one journal row), a
  valid token with a forbidden body (count stays 0). Limit: a pod could try to provoke the provider's rate limit
  with a burst of small calls; the reason code is in the infra record and the runner stops after three such tries.
- The meaning of the version's total cap changed with `d5e1195` and is now written down: reaching it stops the round
  and asks for a person, instead of recording the remaining attempts as budget stops. No archived attempt met it.
- The agent's shell is `bash -c`, not `bash -lc`: the image's `/etc/profile` resets `PATH` for login shells, which
  dropped Go and cost the first `go` command of every Go attempt of the collection, in both versions. A new
  collection differs from the archive in this.
- `checker_git` allows this checkout only (`safe.directory=<path>`), not `*`; reproduced clean on the cluster.

**What this means for the archived collection.** Its pods had no gate, so every preparation, reproduction and agent
pod started inside the window; the VM had no cloud credentials and the pods held no secrets. The published numbers
do not depend on it: the two cluster rounds re-validated all 56 patches with the same outcomes for the main analysis.

**Not determined.** Why the guest returns the false success, and whether it can happen under runc (594 refusals
there showed none); whether another policy enforcer has the window (not run); whether the trace instruments change
the window (no block ran without them); how long before a pod starts the controller learns its address.

**Corrected after review (same day).** The script that explained each accepted SYN matched packets to probe tries by
source address and port only, so a reused port could lend an "allowed" label to a forbidden destination. It now
matches on destination and time as well and never resolves doubt towards "allowed"; recomputed from the raw trace:
still 0 unexplained and 0 ambiguous accepted SYNs among 928,346. Five moved from "allowed" to "start-up window";
the count of late events with a rejecting trace went from 132 to 128 of 133. A second review found the same kind of
weakness in the per-event lookup (a rejected packet of an earlier try could stand in for a later one with the same
address, port and destination); it now works packet by packet and calls an event blocked only when its own packet,
or every packet of that combination, was dropped: 126 rejected, 2 inconclusive, 5 without a trace (above). Details
in the folder's README, "Correction after review" and "Second correction".

The VM ran 1.68 h in three sessions (1.25 h, 0.29 h and 0.14 h) and was stopped after each.
