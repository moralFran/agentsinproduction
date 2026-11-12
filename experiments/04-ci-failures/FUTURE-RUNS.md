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
the call; calls already reserved may still complete and be billed to that run. Setup explicitly restarts the gateway
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
controls live. Its results will be added here as a dated section. Until then this harness is **untested on a cluster**,
and the archived results stand on the harness that produced them.

## Follow-up verification (2026-11-12, after the baseline re-test)

All checks below passed locally on the follow-up implementation:

| Check | Result |
|---|---|
| `python3 -B executor/test_executor.py` | 31/31 |
| `python3 -B infra/test_security.py` | 37 tests, OK |
| `python3 -B infra/test_workflow.py` | 9 tests, OK |
| `python3 -B gateway/test_budget.py --short` | 20 checks, 0 failed |

New regressions exercise token-bound parallel budgets, restart/revocation and closure between lookup and reservation;
Git metadata tampering without executing fsmonitor; retained pre-test file inventories; suites that only query Git;
an ignore file planted in `HOME`; a new self-ignoring directory; the token absent from the tool's environment;
a run closed when its token cannot be read; an unknown reproduction tree; Go compilation, mandatory on the fixed tree and recorded on the broken one;
the maintainer's fix under the agent's dependency cache, from the executor through `repro.sh` to `freeze.py`,
including a command that ends 0 but writes `go.sum` only under that cache;
checkout restoration on broken/hidden reproduction; eligibility decisions and stale digests; gateway rollout ordering;
and the tally's actual round sizes and distinct tree-mutation outcome. Local servers use a fake upstream and make no
provider calls. The earlier re-test record above is retained with its original counts.

The cluster check remains open. On a fresh VM, start with **one Go and one Python case** through preparation,
reproduction and validation, checking cache mounts, init containers, pod cleanup and actual network denial. Only after
that smoke test should the lab reproduce all 11 historical cases and revalidate the 56 non-empty archived patches.
Write comparison results separately, including infrastructure failures, changed outcomes and rejected case controls;
do not overwrite the archive. Unchanged artifact hashes and identical regenerated totals do not establish that these
new runtime checks would preserve every historical classification.
