# Experiment 03 · What can a compromised coding agent reach?

Assume a coding agent with a shell already ran a command it should not have, for example because a prompt injection
in the code or docs it read worked. This lab measures what that command can
reach, one boundary at a time, without the controls and with them: network, cluster permissions, the kernel. Then
whether the agent can still do its job in the locked-down setup, and what the stronger isolation (Kata) costs.
Results: [`results.md`](results.md). Every target is fake; no exploit is attempted.

Names: this is **experiment 03** of the channel and the fourth video (production id `A-v05`, folder `v04-kata`). The
GCP label `experiment=aip-v04-kata` and the folder name come from the production numbering and were kept, because the
recorded results, the captures and the cleanup filter refer to them. "Experiment 03", `v04-kata` and
`experiment=aip-v04-kata` are the same thing.

| Path | What it is |
|---|---|
| `infra/` | create/destroy the two ephemeral VMs (no service account), install k3s + Kata, build the images |
| `k8s/` | plain Kubernetes manifests, applied to the k3s cluster ("k8s" is the usual short name for Kubernetes): namespaces (the agent's and the validator's enforce the `restricted` Pod Security level), the gateway and who may call it, the fake internal API, the NetworkPolicy under test, the RBAC lab, the pods of the agent, the diagnostics and the validator; `check_restricted.py` checks the pod templates against that level offline |
| `gateway/gateway.py` | the only path out of the sandbox: holds the provider key, forwards `POST /v1/messages` only, in a restricted format (text and client tools), an estimated reservation per call written to disk before forwarding, a stop when reported usage exceeds it, logged; a deadline and limits per connection, no redirects followed, its own version header |
| `endpoint/`, `internal-api/` | the "outside" server and the fake internal service with dummy data |
| `diag/` | fixed diagnostics run from the agent's position (network, DNS, RBAC, runtime, final configuration, who reaches the gateway, the gateway against a misbehaving client, the harness's self-check) and tallies |
| `perf/` | start time and idle memory per runtime (20 starts each, alternating) |
| `agent/` | a minimal coding agent (one model loop, one `bash` tool), its fixed self-check, the attempt runner and the report picker |
| `validator/` | decides whether a patch is a fix: allowed paths only, regular files only, pristine everything else, every expected test must run and pass, pytest must exit 0, and the library must behave correctly when called from outside pytest; the reference fix is removed from the pod before patch code runs; negative controls in `controls/` |
| `task/` | the frozen task: a real boltons bug, the failing test, and the maintainer's fix as a control |
| `results/` | raw output of every run, the logs of the gateway, the endpoint and the internal API, the patches |

## Full procedure
On your machine (needs `gcloud`; set `AIP_PROJECT`):
1. `infra/create.sh`: creates the two VMs, labels them and their disks, and writes `lab.env` (zone and the two
   internal addresses; every script reads the addresses from there).
2. Copy this folder to `aip-kata-01`; copy `endpoint/server.py` and `infra/start-endpoint.sh` to one folder on
   `aip-endpoint-01` and run `./start-endpoint.sh` there (absolute path, explicit working directory, self-test).

On `aip-kata-01`, from this folder:
3. `infra/install-k3s-kata.sh`: pinned k3s v1.37.2+k3s1, Helm v3.22.1, Kata 4.3.1; admin kubeconfig 0600. The two
   installer scripts are fetched at a fixed commit and checked against a SHA-256; the header of the script lists what
   is pinned, how, and what is not.
4. `<provider key on stdin> | infra/setup-lab.sh`: namespaces, code ConfigMaps, fake internal API, gateway (the key goes
   from stdin into a Secret, never into a file), who may call the gateway, validator namespace, images
   (`python:3.12-slim` by digest, `anthropic==2.8.0`, `pytest==9.2.0`). It can be run again: a changed `gateway.py`
   replaces the running pod, and the script compares the code inside the pod with the file.
5. Diagnostics. Every run has an id, `RUN`, and writes `results/<name>-$RUN.<ext>`; a script stops rather than
   overwrite a file (the files without a suffix are the collection of 2026-11-11). `RUN=<id> diag/run-net.sh`,
   `diag/run-https.sh`, `diag/run-dns.sh`, `diag/run-rbac.sh`, `diag/run-runtime.sh`, `diag/run-limits.sh`,
   `diag/run-gateway-ingress.sh`, `diag/run-gateway-live.sh`, `diag/run-selfcheck.sh`, and
   `sudo NODE_IP=<node ip> python3 perf/perf.py 20 results/perf-<id>.jsonl` (nothing else running).
6. The task: `agent/run-attempts.sh 5 <round-id>` (a new id per round), then `RUN=<id> diag/run-integration.sh`.
   `validator/revalidate.sh <new out.jsonl> <patches…>` re-checks stored patches and the negative controls without the
   model. The runners need only bash, kubectl and python3 on the node.
7. Back on your machine: copy `results/`, then `infra/destroy.sh` (only this experiment's two VMs).

Offline, no cluster and no provider call: `python3 gateway/test_budget.py` (budget, request format, misbehaving
clients, redirect, headers; fake upstream), `python3 agent/test_agent.py` (the harness and the report picker, with a
stub model and a synthetic folder), `python3 validator/test_validate.py` (the validator's tree checks and external
check on a synthetic library; pytest replaced by a stand-in), `bash diag/test-net-probe.sh`,
`bash infra/test-pod-wait.sh`, `python3 k8s/check_restricted.py`. None of them runs the task's repository.

`infra/list.sh` shows what the experiment created: instances by the filter `destroy.sh` deletes by (the `aip-` prefix
and both labels, defined once in `infra/scope.sh`), disks by their two names. `capture/` holds the terminal captures
of the video: the command list per scene, the player that types and runs them for real, and the recordings.

## Who says what in a result row
An attempt's row (`results/task-<round>.jsonl`) mixes three sources, and only two of them are measurements:
- **measured outside the pod**, by the runner: `pod_phase`, `pod_wall_s`;
- **decided by the validator**, in another pod, from the patch text: `validation`;
- **reported by the agent's pod itself**: everything under `agent` (outcome, model calls, tokens, times, the commands
  and their exit codes). That pod ran commands a model chose, as the same user as the harness, so this is its own
  account. The runner accepts only the report line that carries a nonce it made for that pod, and the harness keeps
  the nonce and its output away from the commands (`agent/agent.py`), which stops a command from slipping in a second
  line; it does not turn the content into a measurement. The gateway's log has the calls and tokens it saw.

The gateway's budget is **one amount for every caller**, and the `x-run-id` in its log is whatever the caller sent.
Nothing is limited or attributed per run by the gateway. A NetworkPolicy (`k8s/15-gateway-ingress.yaml`) limits who
can call it to the agent's pods; among those, the attribution stays self-declared.

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
- **A new pod starts before its policy applies.** Found later on the same software (experiment 04's lab, 2026-11-13):
  until the policy controller has written a new pod's rules (from 0.1 s to 1.8 s, the longest seen there, Kata and runc alike) the pod can
  reach what the policy forbids. This experiment probed a pod that was already running, so it did not see it; an
  init container that waits for the policy closes it (`results.md`, "Found later, in experiment 04's lab").
- **Verified on 2026-11-12 (r4):** the pinned procedure ran from two empty VMs to the end (`results.md`, "Fourth
  review: lab re-run (r4)"). Kata's default configuration does not apply the pod's seccomp profile inside the guest
  (`disable_guest_seccomp = true`). Before that run: the pinned procedure was never re-run from an empty VM (the recorded run used k3s `stable` and the
  latest Kata at the time).

The recorded run (2026-11-11) predates some of these scripts; `results.md` says which results come from the original
collection and which from the corrections made after review. The corrections of the fourth review (2026-11-12) were
written after the lab was deleted: `results.md` lists, for each, whether it was tested offline or still needs a
cluster.
