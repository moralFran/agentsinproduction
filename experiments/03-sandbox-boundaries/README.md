# Experiment 03 · What can a compromised coding agent reach?

Assume a coding agent with a shell already ran a command it should not have, for example because a prompt injection
in the code or docs it read worked. This lab measures what that command can
reach, one boundary at a time, without the controls and with them: network, cluster permissions, the kernel. Then
whether the agent can still do its job in the locked-down setup, and what the stronger isolation (Kata) costs.
Results: [`results.md`](results.md). Every target is fake; no exploit is attempted.

| Path | What it is |
|---|---|
| `infra/` | create/destroy the two ephemeral VMs (no service account), install k3s + Kata, build the images |
| `k8s/` | plain Kubernetes manifests, applied to the k3s cluster ("k8s" is the usual short name for Kubernetes): namespaces, the gateway, the fake internal API, the NetworkPolicy under test, the RBAC lab, the agent's pod |
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

## Where the API key lives
In this lab the provider key is a Kubernetes Secret (`gateway-key`, namespace `lab-gateway`) mounted only into the
gateway pod; `infra/setup-lab.sh` reads it from stdin, so it is never written to a file on the machine. The agent's pod
has no access to that Secret. In production, keep the key in a secret manager (or at least a Secret encrypted at rest),
give the gateway access through its workload identity, and rotate it. The gateway still has the key in memory while it
runs, because it is the component that adds it to the request. The property that matters here is that the key never
enters the agent's sandbox: a hijacked command has nothing to steal there, it can only ask the gateway for a model call.

## Kata on k3s: notes
No manual edit of containerd or k3s was needed. What was specific, and what tripped us:
- **Nested virtualization.** Kata starts a guest VM (QEMU) per pod, so the VM needs it: `--enable-nested-virtualization`
  on an `n2` machine in `infra/create.sh`.
- **The only k3s-specific setting** is the `kata-deploy` chart's `k8sDistribution=k3s` (`infra/install-k3s-kata.sh`).
  It points kata-deploy at k3s's embedded containerd and creates the `kata-qemu` RuntimeClass; a pod opts in with
  `runtimeClassName: kata-qemu`.
- **Images without a registry.** They are imported with `k3s ctr images import` and used with
  `imagePullPolicy: Never`. This kubelet then accepts a local image only under the name it was pulled with: written as
  `docker.io/library/python:3.12-slim@sha256:…` it fails with `ErrImageNeverPull` although the image is on the node.
  That is k3s/kubelet behaviour, not Kata, but it shows up in this registry-less setup (`results.md`, "Found while
  recording the captures").
- **Kubeconfig mode.** k3s writes the admin kubeconfig world-readable (0644) by default; install with
  `--write-kubeconfig-mode 600`.
- **Size for the overhead.** Each Kata sandbox added about 3.5 s to start and about 330 MiB of host memory (mostly
  QEMU), untuned. Several Kata pods on a small node compete for CPU and memory; leave headroom in deadlines.
- **NetworkPolicy works the same.** With flannel and k3s's embedded policy controller, the policy gave the same result
  for Kata and runc pods (10 repetitions each), so moving to Kata does not change how the policy is written.
- **Not verified:** the pinned procedure was never re-run from an empty VM (the recorded run used k3s `stable` and the
  latest Kata at the time).

The recorded run (2026-11-11) predates some of these scripts; `results.md` says which results come from the original
collection and which from the corrections made after review.
