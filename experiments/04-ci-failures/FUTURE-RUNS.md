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
of that cache and writes to a private output; its dependencies are available only to fixed/hidden executor controls.
Python runtimes are also per case. Prepared caches and build products remain untrusted repository output: the host
copies them without executing them, and execution stays in the sandbox.

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
an already modified file is detected. During reproduction, the maintainer's fix now undergoes this **same integrity
check**, for all original and hidden samples. Each sample starts from a restored snapshot with the fix reapplied;
restoration checks file content, so same-size edits within one timestamp tick cannot survive. If the fixed suite
itself leaves unignored reports, coverage files or other changes, an otherwise reproduced case is recorded as
`incompatible_test_side_effects`, with the phase and reason in `integrity_control`. It is excluded before freezing,
not counted as a rejected agent patch. Missing/failed integrity checks are infrastructure errors, and `freeze.py`
refuses any reproduced case without a clean control, including records from the earlier harness.

For eligible cases, persistent tree changes reject the patch. Original-suite mixed results become
`ci_flaky_after_patch`; hidden mixed results become `hidden_tests_flaky`, not automatically `worse`. Only three hidden
failures produce `green_fails_hidden`; three passes produce `green_passes_hidden`. Missing results and timeouts are
infrastructure/timeout outcomes. Each sample starts from the snapshot, independent of earlier samples.

Reproduction now records three hidden runs on the maintainer's fix and three on **broken code plus only the test
changes**. Missing/timed-out samples prevent reproduction; mixed hidden results are intermittent; a consistently
failing hidden suite on the fix prevents inclusion. `hidden_control.discriminates` reports whether all fixed runs
pass and all broken-plus-tests runs fail. Before freezing, inspect a false value: tests may themselves be the fix.
Even a true value does not prove that every hidden assertion concerns the original failure; inspect that relationship
as well. These controls do not replace the rule-9 review illustrated by QuantDinger, scc and yarr.

The archived hidden check ran once, with later audit reruns for failures. It was **not retroactively changed** to this
three-sample rule, and no archived outcome was recomputed with new tests.

## Remaining trust boundary

This is not an adversarially sound proof of correctness. Applied test files must be readable by the test process;
repository code can tamper with its own runner, exit before assertions, modify ignored files, or change and restore
files between snapshots. The same-UID agent loop/result channel is also not a security boundary. Choosing the last
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

The judge accepts verdict writes only as `application/json` with a matching local Origin when supplied; browser
cross-origin and `text/plain` requests are rejected. Non-browser clients may omit Origin. Existing append-only verdict
files and the archive guards are unchanged.

## Verification performed for these changes

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

## Independent re-test of this patch (2026-11-12)

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
