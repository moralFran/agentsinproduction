# Experiment 03 · What can a compromised coding agent reach?

Assume a coding agent with a shell already ran a command it should not have. This lab measures what that command can
reach, one boundary at a time, without the controls and with them: network, cluster permissions, the kernel. Then
whether the agent can still do its job in the locked-down setup, and what the stronger isolation (Kata) costs.
Results: [`results.md`](results.md). Every target is fake; no exploit is attempted.

| Path | What it is |
|---|---|
| `infra/` | create/destroy the two ephemeral VMs (no service account), install k3s + Kata, build the images |
| `k8s/` | namespaces, the gateway, the fake internal API, the NetworkPolicy under test, the RBAC lab, the agent's pod |
| `gateway/gateway.py` | the only path out of the sandbox: holds the provider key, forwards `POST /v1/messages` only, in a restricted format (text and client tools), an estimated reservation per call written to disk before forwarding, a stop when reported usage exceeds it, logged |
| `endpoint/`, `internal-api/` | the "outside" server and the fake internal service with dummy data |
| `diag/` | fixed diagnostics run from the agent's position (network, DNS, RBAC, runtime, final configuration) and tallies |
| `perf/` | start time and idle memory per runtime (20 starts each, alternating) |
| `agent/` | a minimal coding agent (one model loop, one `bash` tool) and the attempt runner |
| `validator/` | decides whether a patch is a fix: allowed paths only, pristine everything else, every expected test must run and pass, pytest must exit 0; negative controls in `controls/` |
| `task/` | the frozen task: a real boltons bug, the failing test, and the maintainer's fix as a control |
| `results/` | raw output of every run, the logs of the gateway, the endpoint and the internal API, the patches |

## Full procedure
On your machine (needs `gcloud`; set `AIP_PROJECT`):
1. `infra/create.sh`: creates the two VMs and writes `lab.env` (zone and the two internal addresses).
2. Copy this folder to `aip-kata-01`; copy `endpoint/server.py` and `infra/start-endpoint.sh` to one folder on
   `aip-endpoint-01` and run `./start-endpoint.sh` there (absolute path, explicit working directory, self-test).

On `aip-kata-01`, from this folder:
3. `infra/install-k3s-kata.sh`: pinned k3s v1.37.2+k3s1, Helm v3.22.1, Kata 4.3.1; admin kubeconfig 0600.
4. `<provider key on stdin> | infra/setup-lab.sh`: namespaces, code ConfigMaps, fake internal API, gateway (the key goes
   from stdin into a Secret, never into a file), validator namespace, images (`python:3.12-slim` by digest,
   `anthropic==2.8.0`, `pytest==9.2.0`).
5. Diagnostics, each writing to `results/`: `diag/run-net.sh`, `diag/run-https.sh`, `diag/run-dns.sh`,
   `diag/run-rbac.sh`, `diag/run-runtime.sh`, `sudo NODE_IP=<node ip> python3 perf/perf.py 20 results/perf.jsonl`
   (nothing else running), `diag/run-limits.sh`.
6. The task: `agent/run-attempts.sh 5 <round-id>` (a new id per round), then `diag/run-integration.sh`.
   `validator/revalidate.sh <out.jsonl> <patches…>` re-checks stored patches and the negative controls without the model.
7. Back on your machine: copy `results/`, then `infra/destroy.sh` (only this experiment's two VMs).

`gateway/test_budget.py` tests the gateway's budget and request format offline against a fake upstream.
`infra/list.sh` shows what the experiment created (the filter `destroy.sh` acts on). `capture/` holds the terminal
captures of the video: the command list per scene, the player that types and runs them for real, and the recordings.

The recorded run (2026-11-11) predates some of these scripts; `results.md` says which results come from the original
collection and which from the corrections made after review.
