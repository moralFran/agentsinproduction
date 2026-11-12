# Network and pod controls on the cluster, follow-up round (2026-11-12)

Every pod below was built with the harness's own spec builder (`cases/pod.py build_spec`, `cases/prep.py worker_spec`); only the command
of the main container was replaced by the probe (`controls/netprobe.py`), and CPU/memory *requests* were lowered. Raw logs: `network/`.
The probe prints status codes and sizes only. The control pod (namespace `default`, Kata, no NetworkPolicy) is the positive control:
what is reachable when no policy applies.

## 1. One full probe per pod kind (first seconds of the pod included)

| Target | control: namespace `default`, no policy | `ci-prep` (preparation) | `ci-agent` (agent) | `ci-exec` (repro, no init container) | `ci-exec` (repro fixed) | `ci-exec` (repro fixed-agent-cache) | `ci-exec` validation, test container (suite) | `ci-exec` validation, test container (hidden) |
|---|---|---|---|---|---|---|---|---|
| DNS lookup of proxy.golang.org | resolved | resolved | no DNS | resolved | resolved | resolved | no DNS | no DNS |
| download https://proxy.golang.org/github.com/gobwas/pool/@v/v0.2.1.zip | http 200 (13438 B) | http 200 (13438 B) | no DNS | http 200 (13438 B) | http 200 (13438 B) | http 200 (13438 B) | no DNS | no DNS |
| download https://pypi.org/simple/pytest/ | http 200 (134449 B) | http 200 (134449 B) | no DNS | http 200 (134449 B) | http 200 (134449 B) | http 200 (134449 B) | no DNS | no DNS |
| download http://example.com/ | http 200 (577 B) | http 200 (577 B) | no DNS | http 200 (577 B) | no DNS | http 200 (577 B) | no DNS | no DNS |
| TCP public address, port 443 (1.1.1.1:443) | open | open | refused | open | refused | open | refused | refused |
| TCP public address, port 53 (not 80/443) (1.1.1.1:53) | open | refused | refused | open | refused | open | refused | refused |
| TCP cloud metadata endpoint (169.254.169.254:80) | open | refused | refused | open | refused | open | refused | refused |
| TCP node private address, ssh (10.128.0.7:22) | open | refused | refused | open | refused | open | refused | refused |
| TCP node private address, Kubernetes API (10.128.0.7:6443) | open | refused | refused | refused | refused | open | refused | refused |
| TCP node private address, kubelet (10.128.0.7:10250) | open | refused | refused | refused | refused | open | refused | refused |
| TCP Kubernetes API ClusterIP (10.43.0.1:443) | open | refused | refused | refused | refused | open | refused | refused |
| TCP gateway ClusterIP, model port (10.43.210.10:8080) | refused | refused | open | refused | refused | refused | refused | refused |
| TCP gateway ClusterIP, admin port (10.43.210.10:8081) | refused | refused | refused | refused | refused | refused | refused | refused |
| TCP gateway pod address, model port (10.42.0.21:8080) | refused | refused | open | refused | refused | refused | refused | refused |
| TCP gateway pod address, admin port (10.42.0.21:8081) | refused | refused | refused | refused | refused | refused | refused | refused |
| TCP another pod (metrics-server) (10.42.0.4:10250) | open | refused | refused | refused | refused | open | refused | refused |
| TCP DNS pod, tcp 53 (10.42.0.2:53) | open | open | refused | refused | refused | open | refused | refused |
| HTTP GET to the metadata endpoint | http 200 | refused | refused | refused | refused | http 200 | refused | refused |
| HTTP GET gateway /healthz (model port) | refused | refused | http 200 | refused | refused | refused | refused | refused |
| HTTP GET gateway admin /state, no token | refused | refused | refused | refused | refused | refused | refused | refused |
| POST /v1/messages with an unknown run id | refused | refused | http 403 | refused | refused | refused | refused | refused |

Read with section 2: the probe starts with DNS and the downloads, so the pods whose first lines say `http 200` and later lines say
`refused` (`ci-agent`, `ci-exec` repro) were inside the start-up window described below; `ci-exec` (repro fixed) ran its whole probe inside it.

### What each container is and can read

| Pod | uid:gid | Guest kernel | Seccomp | NoNewPrivs | CapEff | Mounts (ro/rw) | Readable | Not present |
|---|---|---|---|---|---|---|---|---|
| control: namespace `default`, no policy | 1000:1000 | 6.18.56 | 0 | 0 | 0000000000000000 |  |  | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-prep` (preparation) | 1001:1002 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, /input ro, <case> rw, /srv/ci/uv rw, /tmp rw |  | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-agent` (agent) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw | <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` (repro, no init container) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw | <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` (repro fixed) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, /in/fix.diff ro, /in/hidden.diff ro, <case> ro, <case>/gomod ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw | /in, /in/hidden.diff, /in/fix.diff, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` (repro fixed-agent-cache) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, /in/fix.diff ro, /in/hidden.diff ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw | /in, /in/hidden.diff, /in/fix.diff, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` validation, test container (suite) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw, /validation ro | /validation/prepared.json, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` validation, test container (hidden) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw, /validation ro | /validation/prepared.json, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |

`<case>` = `/srv/ci/cases/gobwas-ws-a567dfd6`, `<secret>` = `/srv/ci/secret/gobwas-ws-a567dfd6`. Host kernel 7.0.0-1017-gcp; a guest kernel of 6.18.56 shows the Kata VM.
`Seccomp: 0` inside the guest in every pod although the pod spec asks for `RuntimeDefault` (same as experiment 03).

## 2. When the policy starts to apply to a new pod (`controls/nettime.py`)

`-fu*`: 12 s probes at the end of the follow-up round, with nothing else running. The first round has the larger sample (`../integration-2026-11-12/network-controls.md`).

Times are seconds after the container's process started. "never" = blocked from the first try; "always" = reachable in every try.
Expected once the policy applies: ci-exec nothing; ci-agent only the gateway model port; ci-prep only public 80/443 and DNS.

| Pod | public | metadata | node ssh | kubernetes api clusterip | dns pod tcp 53 | gateway model port | gateway admin port |
|---|---|---|---|---|---|---|---|
| agent-fu1 | 3 of 7 tries; last reachable 0.63 s; first blocked 2.95 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 1.65 s | 5 of 7 tries; last reachable 13.87 s; first blocked 0.02 s | never |
| agent-fu2 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | 4 of 6 tries; last reachable 11.56 s; first blocked 0.02 s | never |
| exec-fixed-agent-cache-fu1 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | never | never |
| exec-fixed-agent-cache-fu2 | never | never | never | never | never | never | never |
| exec-repro-fu1 | 3 of 7 tries; last reachable 0.63 s; first blocked 0.95 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.95 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.95 s | 3 of 7 tries; last reachable 0.65 s; first blocked 2.95 s | 3 of 7 tries; last reachable 0.65 s; first blocked 3.95 s | never | never |
| exec-repro-fu2 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.63 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 2.64 s | never | never |
| exec-validate-suite-fu1 | never | never | 1 of 4 tries; last reachable 0.01 s; first blocked 2.31 s | never | never | 1 of 4 tries; last reachable 10.93 s; first blocked 0.01 s | never |
| exec-validate-suite-fu2 | never | never | 1 of 4 tries; last reachable 0.01 s; first blocked 2.31 s | never | never | never | never |
| prep-fu1 | always | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 3 of 7 tries; last reachable 11.92 s; first blocked 0.65 s | always | never | never |
| prep-fu2 | always | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.33 s; first blocked 0.65 s | always | never | never |


### Start-up window, per pod kind

A pod counts as "had a window" when the public address, the metadata endpoint, the node or the Kubernetes API ClusterIP (for `ci-prep`: the last three)
answered at least once although the namespace's policy forbids it. The probe samples every ~0.3 s, so "last reachable 0.65 s" means blocked by ~1.0 s.

| Pod kind | Condition | Pods | Had a window | Last reachable, min to max (s) |
|---|---|---|---|---|
| agent | idle | 2 | 2 | 0.34 to 0.63 |
| exec-fixed-agent-cache | idle | 2 | 1 | 0.33 to 0.33 |
| exec-repro | idle | 2 | 2 | 0.33 to 0.65 |
| exec-validate-suite | idle | 2 | 2 | 0.01 to 0.01 |
| prep | idle | 2 | 2 | 0.33 to 0.33 |

### Other single observations in the timing probes

- `agent-fu1`: agent refused on the gateway model port 2 time(s), first at 0.02 s (expected reachable)
- `agent-fu2`: agent refused on the gateway model port 2 time(s), first at 0.02 s (expected reachable)
- `exec-validate-suite-fu1`: gateway model port reachable 1 time(s), last at 10.93 s
- `prep-fu1`: kubernetes api clusterip still reachable at 11.92 s

## 3. Five minutes of steady state while other pods were created and deleted (`controls/netflap.py`)

One connection attempt per target every ~0.2 s (0.5 s timeout). "after 5 s" excludes the start-up window.

| Pod | Target | Tries | Reachable | Reachable after 5 s | Blocked after 5 s |
|---|---|---|---|---|---|
