# Experiment 04 · cluster integration of the hardened harness (2026-11-12, fresh VM)

The harness of experiment 04 was hardened on 2026-11-12, **after** the collection (see `../../FUTURE-RUNS.md`), and until this run
it had only passed local tests with stand-ins. This folder is the first run of that harness on a real cluster: a fresh GCP VM
(n2-standard-8, Ubuntu 24.04, k3s v1.37.2+k3s1, Kata 4.3.1 with `kata-qemu`), built from an empty machine with the current scripts.

**Nothing here is a re-classification.** The 66 archived attempts, their patches, the frozen `cases/cases.csv` and the verdicts were
read and never written. The archived outcomes stand on the harness that produced them. The two agent attempts in `attempts/` are an
**integration check, not data**.

The run happened in a fresh run folder made on the VM with `infra/new-run.sh <dir> --with-candidates`; its candidate files were then
reduced to the 11 frozen records (`frozen-candidates/`, taken from `mining/candidates-*.jsonl` by repository and broken commit).

## Answers

Harness revision tested: private commit `1160dcd` (public copy `ecdbcd7`), the hardening of 2026-11-12. The later follow-up hardening
(private `98717cf`, public `dec7c18`) was committed while this run was in progress and is **not** what ran here.

VM on from 17:31:05Z to 20:47:32Z (3.27 h). No harness script failed and no harness file was changed.

1. **Does the lab come up from an empty VM? Yes.** `create.sh` (17:30:50Z), then on the VM `install-docker.sh` (26 s), `install-k3s-kata.sh`
   (2 min 19 s), `build-images.sh` (1 min 28 s), `setup-lab.sh` with the provider key on stdin (11 s, it calls `code-configmap.sh`). Gateway
   rolled out at 17:37:04Z, six minutes after the VM existed. Evidence: `setup/`.
2. **Do the new pods work under Kata? Yes.** Preparation pods ran as the VM user (uid 1001, gid 1002) with only `/input` (read-only), the
   per-case output and `/tmp`; no `/in`, no `/srv/ci/secret`. Validation pods ran the init container (`validate-prepare`, exit 0) and the
   test container saw the patched tree, `/validation/prepared.json` read-only, and **no** `/in/*` and no `/srv/ci/secret`; the fixed-tree Go
   cache is mounted only in hidden/fixed pods. Guest kernel 6.18.56 against host 7.0.0. **`Seccomp: 0`** in `/proc/self/status` in every pod
   kind (with `NoNewPrivs: 1`, `CapEff: 0`), as in experiment 03. Evidence: `pods/`, `network-controls.md`, 229 pod logs.
3. **Do the network controls hold? In steady state yes, with positive controls; in the first second of a pod's life no.**
   - `ci-prep`: public HTTPS downloads work (a Go module zip, the PyPI index; the 11 real preparations); the node's private address, the
     metadata endpoint, the Kubernetes API and the gateway's ClusterIP are refused. The same targets answer from a pod with no policy.
   - Gateway ingress: a `ci-agent` pod reaches 8080 (`/healthz` 200; unknown run id 403); pods in `default`, `ci-prep` and `ci-exec` are refused on
     8080 and 8081. From the host: 401 without the token or with a wrong one; 400 for caps 0.34, 1000, NaN, Infinity, 1e999, "nan", 0, -1 and a
     missing cap; 200 with the token (state, open, read, close). Evidence: `gateway/admin-controls.txt`.
   - Executor pods have no network and agent pods reach only the gateway's model port, **once the policy applies**.
   - **Finding (start-up window):** k3s's network policy controller (kube-router v2.11.1-k3s1) applies a namespace's policy to a new pod
     some tenths of a second after its first process starts. In 24 of 31 timed pods without an init container (`ci-agent`, `ci-exec` repro,
     `ci-prep`) the public internet, the metadata endpoint, the node and the Kubernetes API answered for the first 0.3 to 0.7 s, busy or idle;
     one `ci-exec` "repro fixed" pod ran a whole probe (three downloads, metadata, node) before the policy applied. Validation test containers
     start after the init container and had no such window in 8 of 8 pods. In the same first moments agent pods were refused by the gateway.
   - **Finding (single connections):** in about 2,700 steady-state tries from a `ci-exec` pod (five minutes, six targets), one connection to the Kubernetes API ClusterIP
     succeeded (at 149 s); another succeeded from a validation test container (at 6.6 s); pods outside `ci-agent` connected once to the
     gateway's model port (one pod) and once each to its admin port (three pods), which answers 401 without the token. Cause not investigated.
     This predates the hardening: the archived collection used the same cluster software and policies. Evidence: `network-controls.md`.
4. **Do the 11 frozen cases still prepare and reproduce? Yes, 11 of 11 `reproduced`** (broken 3/3 fail, fixed 3/3 pass), `integrity_control`
   clean in all, none `incompatible_test_side_effects`. `hidden_control.discriminates`: true in 7 (QuantDinger, mcp-go, gobwas/ws, cosign,
   scrapy-redis, minify, miniredis); **false in boyter/scc and nkanaev/yarr** (the hidden tests pass on broken code plus only the test changes);
   ludwig and pyinfra have no hidden tests. `freeze.py` froze 11; its `cases.csv` has the same rows as the archive except **yarr, which now
   has hidden tests** (`fixtures/` counts as test data), and a different row order. Evidence: `repro-compare.md`, `freeze/`.
5. **Do the archived patches get the same outcome? 56 of 56 non-empty patches re-validated (36 distinct): 50 the same, 6 different.** The six
   are all nkanaev/yarr (v1 and v2, r1 to r3): `green_no_hidden_tests` → `green_fails_hidden`, suite 3/3, hidden 0/3, because the case now has
   a hidden test. yarr is outside the main analysis. No `ci_flaky_after_patch`, `hidden_tests_flaky`, `rejected_by_validator`, timeout or
   infrastructure error occurred. Main-analysis numbers with the new validator's outcomes: 48 attempts, 30 green, 4 failing the hidden
   tests (all gobwas/ws), v1 15 and v2 15: **unchanged**. Evidence: `revalidation.md`, `revalidation.csv`, `revalidation/`.
6. **Validator controls: pass.** A comment appended to `cipher_test.go` and a new `.github/workflows/x.yml` on gobwas/ws were both
   `rejected_by_validator` in the init container. The probe (archived QuantDinger patch v1-a352a7c0-r3 plus code that tries to open the four
   paths when the tests import it) printed `hidden.diff: not readable; fix.diff: not readable; patch.diff: not readable; secret meta.json:
   not readable` as the last output line of all six samples (3 suite, 3 hidden). The same read succeeds where the file is mounted on purpose
   (`/in/fix.diff` in a "repro fixed" pod). Evidence: `validator-controls/`.
7. **Two integration attempts (NOT data): both completed.** `v1-int` (prompt-v1): 9 model calls, US$0.1039, patch validated
   `green_fails_hidden` (3/3, 0/3). `v2-int` (prompt-v2): 11 calls, US$0.1408, `green_passes_hidden` (3/3, 3/3). Gateway total US$0.2447 in 20
   requests, cap 0.33 each. Runs opened and closed with the admin token; with a wrong key `run-round.sh` stopped at repetition 1 with exit 123
   and no journal (pipefail); piped commands inside the agent returned 127 and 1; a repeated attempt was skipped with exit 0 and no spend;
   `check-round.py` reported both one-attempt rounds incomplete (exit 1) and the archived rounds complete (33 each, exit 0). Evidence: `attempts/`.

Not verified here: a complete fresh round through `run-round.sh` (33 attempts) and its resume after a real interruption; the full 113-candidate
pipeline; the outcomes `incompatible_test_side_effects`, `ci_flaky_after_patch`, `hidden_tests_flaky` and `did_not_apply` on real cases (none
occurred); the gateway's connection limits, idle timeouts, redirect refusal and total-budget halt (local tests only); the judge; a mitigation
for the start-up window. Also seen, and older than the hardening: the agent's `bash -lc` drops `/usr/local/go/bin` from `PATH`, so the first
`go` command of an attempt returns 127 until the agent exports the path (both integration attempts; also in the archive).

## What is in this folder

| Path | What |
|---|---|
| `setup/` | logs of `new-run.sh`, `install-docker.sh`, `install-k3s-kata.sh`, `build-images.sh`, `setup-lab.sh` and the cluster state after setup |
| `prep/`, `repro/` | the three `cases/pipeline.sh` workers, `prep.jsonl`, `repro.jsonl` of the fresh run (11 cases) |
| `repro-compare.md` | reproduction of the 11 cases next to the archive, with `hidden_control` and `integrity_control` |
| `freeze/` | `freeze.py` on the fresh run, row-by-row comparison of its `cases.csv` with the archived one, the archive guard on the VM copy |
| `fresh-run/` | `cases.csv`, `intermittent.csv`, `not-reproduced.csv` and the `FRESH_RUN` marker of the fresh run folder |
| `pods/` | a live preparation pod (spec and `kubectl exec`: uid, seccomp, mounts) and host permissions under `/srv/ci` |
| `network/` | one full probe per pod kind (`probe-*.log`, spec used in `*.spec.json`), `timing/` (when the policy starts to apply), `steady/` (5 minutes under pod churn) |
| `network-controls.md` | the tables built from `network/` |
| `gateway/admin-controls.txt` | admin port with and without the token, invalid caps, one run opened and closed |
| `revalidation/` | one JSON per distinct archived patch (the new validator's full record), the journal `revalidation.jsonl`, driver logs |
| `revalidation.csv`, `revalidation.md` | one row per archived attempt: archived outcome, new outcome, 3/3 counts, same or different |
| `validator-controls/` | the three control patches and the validator's output for each |
| `attempts/` | the two integration attempts (NOT data): journals, patches, the gateway's log, the round-runner and resume controls, `check-round.py` |
| `pod-logs/` | `/srv/ci/logs` of the VM: the `EXECUTOR`/`RESULT` line of every harness pod of this run |
| `controls/` | the scripts written for this run (probes, drivers, table builders). They are not part of the harness |

User name, external address and project id were replaced by `<user>`, `<external-ip>`, `<project>` in the copied logs. Addresses left
in the files: cluster ranges (10.x), and the well-known probe targets 1.1.1.1 and 169.254.169.254.
