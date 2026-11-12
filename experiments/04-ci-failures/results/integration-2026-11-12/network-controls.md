# Network and pod controls on the cluster (2026-11-12)

Every pod below was built with the harness's own spec builder (`cases/pod.py build_spec`, `cases/prep.py worker_spec`); only the command
of the main container was replaced by the probe (`controls/netprobe.py`), and CPU/memory *requests* were lowered. Raw logs: `network/`.
The probe prints status codes and sizes only. The control pod (namespace `default`, Kata, no NetworkPolicy) is the positive control:
what is reachable when no policy applies.

## 1. One full probe per pod kind (first seconds of the pod included)

| Target | control: namespace `default`, no policy | `ci-prep` (preparation) | `ci-agent` (agent) | `ci-exec` (repro, no init container) | `ci-exec` (repro fixed) | `ci-exec` validation, test container (suite) | `ci-exec` validation, test container (hidden) |
|---|---|---|---|---|---|---|---|
| DNS lookup of proxy.golang.org | resolved | resolved | resolved | resolved | resolved | no DNS | no DNS |
| download https://proxy.golang.org/github.com/gobwas/pool/@v/v0.2.1.zip | http 200 (13438 B) | http 200 (13438 B) | http 200 (13438 B) | http 200 (13438 B) | http 200 (13438 B) | no DNS | no DNS |
| download https://pypi.org/simple/pytest/ | http 200 (134449 B) | http 200 (134449 B) | http 200 (134449 B) | http 200 (134449 B) | http 200 (134449 B) | no DNS | no DNS |
| download http://example.com/ | http 200 (577 B) | http 200 (577 B) | no DNS | no DNS | http 200 (577 B) | no DNS | no DNS |
| TCP public address, port 443 (1.1.1.1:443) | open | open | refused | refused | open | refused | refused |
| TCP public address, port 53 (not 80/443) (1.1.1.1:53) | open | refused | refused | refused | open | refused | refused |
| TCP cloud metadata endpoint (169.254.169.254:80) | open | refused | refused | refused | open | refused | refused |
| TCP node private address, ssh (10.128.0.7:22) | open | refused | refused | refused | open | refused | refused |
| TCP node private address, Kubernetes API (10.128.0.7:6443) | open | refused | refused | refused | open | refused | refused |
| TCP node private address, kubelet (10.128.0.7:10250) | open | refused | refused | refused | open | refused | refused |
| TCP Kubernetes API ClusterIP (10.43.0.1:443) | open | refused | refused | refused | open | refused | refused |
| TCP gateway ClusterIP, model port (10.43.210.10:8080) | refused | refused | open | refused | refused | refused | refused |
| TCP gateway ClusterIP, admin port (10.43.210.10:8081) | refused | refused | refused | refused | refused | refused | refused |
| TCP gateway pod address, model port (10.42.0.13:8080) | refused | refused | open | refused | refused | refused | refused |
| TCP gateway pod address, admin port (10.42.0.13:8081) | refused | refused | refused | refused | refused | refused | refused |
| TCP another pod (metrics-server) (10.42.0.8:10250) | open | refused | refused | refused | open | refused | refused |
| TCP DNS pod, tcp 53 (10.42.0.6:53) | open | open | refused | refused | open | refused | refused |
| HTTP GET to the metadata endpoint | http 200 | refused | refused | refused | http 200 | refused | refused |
| HTTP GET gateway /healthz (model port) | refused | refused | http 200 | refused | refused | refused | refused |
| HTTP GET gateway admin /state, no token | refused | refused | refused | refused | refused | refused | refused |
| POST /v1/messages with an unknown run id | refused | refused | http 403 | refused | refused | refused | refused |

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
| `ci-exec` validation, test container (suite) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw, /validation ro | /validation/prepared.json, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |
| `ci-exec` validation, test container (hidden) | 1000:1000 | 6.18.56 | 0 | 1 | 0000000000000000 | /code ro, <case> ro, <case>/gomod ro, <case>/repo rw, /srv/ci/uv ro, /tmp rw, /validation ro | /validation/prepared.json, <case>/meta.json, <case>/snapshot, <case>/repo | /in/patch.diff, /in/hidden.diff, /in/fix.diff, <secret>/meta.json, /srv/ci/admin-key |

`<case>` = `/srv/ci/cases/gobwas-ws-a567dfd6`, `<secret>` = `/srv/ci/secret/gobwas-ws-a567dfd6`. Host kernel 7.0.0-1017-gcp; a guest kernel of 6.18.56 shows the Kata VM.
`Seccomp: 0` inside the guest in every pod although the pod spec asks for `RuntimeDefault` (same as experiment 03).

## 2. When the policy starts to apply to a new pod (`controls/nettime.py`)

`-t1`: 40 s probe; `-busy*`: 12 s probes while preparation and reproduction pods were running; `-idle*`: 12 s probes with nothing else running.

Times are seconds after the container's process started. "never" = blocked from the first try; "always" = reachable in every try.
Expected once the policy applies: ci-exec nothing; ci-agent only the gateway model port; ci-prep only public 80/443 and DNS.

| Pod | public | metadata | node ssh | kubernetes api clusterip | dns pod tcp 53 | gateway model port | gateway admin port |
|---|---|---|---|---|---|---|---|
| agent-busy1 | 3 of 6 tries; last reachable 0.65 s; first blocked 0.97 s | 3 of 6 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 6 tries; last reachable 0.67 s; first blocked 2.97 s | 3 of 6 tries; last reachable 0.67 s; first blocked 3.97 s | 3 of 6 tries; last reachable 0.67 s; first blocked 5.98 s | 4 of 6 tries; last reachable 13.59 s; first blocked 0.03 s | never |
| agent-busy2 | never | never | never | never | never | always | never |
| agent-busy3 | 3 of 7 tries; last reachable 0.65 s; first blocked 0.98 s | 3 of 7 tries; last reachable 0.67 s; first blocked 1.98 s | 3 of 7 tries; last reachable 0.67 s; first blocked 2.98 s | 3 of 7 tries; last reachable 0.67 s; first blocked 2.98 s | 3 of 7 tries; last reachable 0.68 s; first blocked 3.99 s | 4 of 7 tries; last reachable 13.93 s; first blocked 0.03 s | never |
| agent-busy4 | 3 of 7 tries; last reachable 0.65 s; first blocked 0.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 2.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 3.97 s | 4 of 7 tries; last reachable 12.9 s; first blocked 0.03 s | never |
| agent-idle1 | never | never | never | never | never | always | never |
| agent-idle2 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 2.64 s | 4 of 6 tries; last reachable 12.56 s; first blocked 0.02 s | never |
| agent-idle3 | 3 of 7 tries; last reachable 0.64 s; first blocked 2.96 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 1.66 s | 5 of 7 tries; last reachable 13.88 s; first blocked 0.02 s | never |
| agent-idle4 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 1.64 s | 3 of 6 tries; last reachable 2.64 s; first blocked 5.95 s | 4 of 6 tries; last reachable 11.56 s; first blocked 0.02 s | never |
| agent-t1 | 3 of 15 tries; last reachable 0.66 s; first blocked 0.98 s | 3 of 15 tries; last reachable 0.67 s; first blocked 1.98 s | 3 of 15 tries; last reachable 0.68 s; first blocked 1.98 s | 3 of 15 tries; last reachable 0.68 s; first blocked 2.98 s | 3 of 15 tries; last reachable 0.68 s; first blocked 3.99 s | 12 of 15 tries; last reachable 40.37 s; first blocked 0.03 s | never |
| exec-fixed-idle1 | never | never | never | never | never | never | 1 of 4 tries; last reachable 0.01 s; first blocked 3.31 s |
| exec-fixed-idle2 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | never | never |
| exec-fixed-idle3 | 3 of 6 tries; last reachable 0.64 s; first blocked 2.96 s | 3 of 6 tries; last reachable 0.65 s; first blocked 2.96 s | 3 of 6 tries; last reachable 0.65 s; first blocked 3.96 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.66 s | never | never |
| exec-fixed-idle4 | 3 of 6 tries; last reachable 0.64 s; first blocked 0.95 s | 3 of 6 tries; last reachable 0.65 s; first blocked 1.95 s | 3 of 6 tries; last reachable 0.65 s; first blocked 1.96 s | 3 of 6 tries; last reachable 0.65 s; first blocked 2.96 s | 3 of 6 tries; last reachable 0.65 s; first blocked 3.96 s | never | never |
| exec-repro-busy1 | 3 of 7 tries; last reachable 0.66 s; first blocked 0.98 s | 3 of 7 tries; last reachable 0.67 s; first blocked 1.98 s | 3 of 7 tries; last reachable 0.67 s; first blocked 1.98 s | 3 of 7 tries; last reachable 0.68 s; first blocked 2.98 s | 3 of 7 tries; last reachable 0.68 s; first blocked 3.99 s | 1 of 7 tries; last reachable 0.03 s; first blocked 0.35 s | never |
| exec-repro-busy2 | 3 of 6 tries; last reachable 0.65 s; first blocked 0.96 s | 3 of 6 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 6 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 6 tries; last reachable 0.66 s; first blocked 2.97 s | 3 of 6 tries; last reachable 0.66 s; first blocked 3.97 s | never | never |
| exec-repro-busy3 | 3 of 6 tries; last reachable 0.64 s; first blocked 0.96 s | 3 of 6 tries; last reachable 0.66 s; first blocked 1.96 s | 3 of 6 tries; last reachable 0.66 s; first blocked 1.96 s | 3 of 6 tries; last reachable 0.66 s; first blocked 2.97 s | 3 of 6 tries; last reachable 0.66 s; first blocked 3.97 s | never | never |
| exec-repro-busy4 | 3 of 7 tries; last reachable 0.65 s; first blocked 0.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 2.97 s | 3 of 7 tries; last reachable 0.66 s; first blocked 3.98 s | never | never |
| exec-repro-idle1 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | never | never |
| exec-repro-idle2 | never | never | never | never | never | never | never |
| exec-repro-idle3 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | never | never |
| exec-repro-idle4 | 2 of 6 tries; last reachable 0.32 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.33 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 0.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 1.64 s | 2 of 6 tries; last reachable 0.34 s; first blocked 2.64 s | never | 1 of 6 tries; last reachable 0.02 s; first blocked 0.34 s |
| exec-repro-t1 | 3 of 14 tries; last reachable 0.65 s; first blocked 0.97 s | 3 of 14 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 14 tries; last reachable 0.66 s; first blocked 1.97 s | 3 of 14 tries; last reachable 0.67 s; first blocked 2.97 s | 3 of 14 tries; last reachable 0.67 s; first blocked 3.98 s | never | never |
| exec-validate-suite-busy1 | never | never | never | never | never | never | never |
| exec-validate-suite-busy2 | never | never | never | never | never | never | never |
| exec-validate-suite-busy3 | never | never | never | never | never | never | never |
| exec-validate-suite-busy4 | never | never | never | never | never | never | never |
| exec-validate-suite-idle1 | never | never | never | never | never | never | never |
| exec-validate-suite-idle2 | never | never | never | never | never | never | never |
| exec-validate-suite-idle3 | never | never | never | never | never | never | never |
| exec-validate-suite-idle4 | never | never | never | 1 of 4 tries; last reachable 6.62 s; first blocked 0.01 s | never | never | never |
| prep-busy1 | always | 3 of 7 tries; last reachable 0.65 s; first blocked 0.97 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.97 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.97 s | always | never | never |
| prep-busy2 | always | never | never | never | always | never | never |
| prep-busy3 | always | never | never | never | always | never | never |
| prep-busy4 | always | never | never | never | always | never | 1 of 6 tries; last reachable 2.35 s; first blocked 0.03 s |
| prep-idle1 | always | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | always | never | never |
| prep-idle2 | always | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | always | never | never |
| prep-idle3 | always | 3 of 7 tries; last reachable 0.65 s; first blocked 0.96 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.96 s | 3 of 7 tries; last reachable 0.65 s; first blocked 1.97 s | always | never | never |
| prep-idle4 | always | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | 2 of 7 tries; last reachable 0.34 s; first blocked 0.65 s | always | never | never |
| prep-t1 | always | 3 of 15 tries; last reachable 0.66 s; first blocked 0.98 s | 3 of 15 tries; last reachable 0.66 s; first blocked 1.98 s | 3 of 15 tries; last reachable 0.66 s; first blocked 1.99 s | always | never | never |


### Start-up window, per pod kind

A pod counts as "had a window" when the public address, the metadata endpoint, the node or the Kubernetes API ClusterIP (for `ci-prep`: the last three)
answered at least once although the namespace's policy forbids it. The probe samples every ~0.3 s, so "last reachable 0.65 s" means blocked by ~1.0 s.

| Pod kind | Condition | Pods | Had a window | Last reachable, min to max (s) |
|---|---|---|---|---|
| agent | busy | 5 | 4 | 0.66 to 0.68 |
| agent | idle | 4 | 3 | 0.33 to 0.64 |
| exec-fixed | idle | 4 | 3 | 0.34 to 0.65 |
| exec-repro | busy | 5 | 5 | 0.66 to 0.68 |
| exec-repro | idle | 4 | 3 | 0.34 to 0.34 |
| exec-validate-suite | busy | 4 | 0 | - |
| exec-validate-suite | idle | 4 | 0 | - |
| prep | busy | 5 | 2 | 0.65 to 0.66 |
| prep | idle | 4 | 4 | 0.34 to 0.65 |

### Other single observations in the timing probes

- `agent-busy1`: agent refused on the gateway model port 2 time(s), first at 0.03 s (expected reachable)
- `agent-busy3`: agent refused on the gateway model port 3 time(s), first at 0.03 s (expected reachable)
- `agent-busy4`: agent refused on the gateway model port 3 time(s), first at 0.03 s (expected reachable)
- `agent-idle2`: agent refused on the gateway model port 2 time(s), first at 0.02 s (expected reachable)
- `agent-idle3`: agent refused on the gateway model port 2 time(s), first at 0.02 s (expected reachable)
- `agent-idle4`: agent refused on the gateway model port 2 time(s), first at 0.02 s (expected reachable)
- `agent-idle4`: dns pod tcp 53 still reachable at 2.64 s
- `agent-t1`: agent refused on the gateway model port 3 time(s), first at 0.03 s (expected reachable)
- `exec-fixed-idle1`: gateway admin port reachable 1 time(s), last at 0.01 s
- `exec-repro-busy1`: gateway model port reachable 1 time(s), last at 0.03 s
- `exec-repro-idle4`: gateway admin port reachable 1 time(s), last at 0.02 s
- `exec-validate-suite-idle4`: kubernetes api clusterip still reachable at 6.62 s
- `prep-busy4`: gateway admin port reachable 1 time(s), last at 2.35 s

## 3. Five minutes of steady state while other pods were created and deleted (`controls/netflap.py`)

One connection attempt per target every ~0.2 s (0.5 s timeout). "after 5 s" excludes the start-up window.

| Pod | Target | Tries | Reachable | Reachable after 5 s | Blocked after 5 s |
|---|---|---|---|---|---|
| agent-steady | public 1.1.1.1:443 | 459 | 4 | 0 | 449 |
| agent-steady | metadata 169.254.169.254:80 | 471 | 4 | 0 | 461 |
| agent-steady | node ssh | 475 | 4 | 0 | 462 |
| agent-steady | kubernetes api clusterip | 492 | 4 | 0 | 482 |
| agent-steady | gateway model port | 1488 | 1484 | 1465 | 0 |
| agent-steady | gateway admin port | 470 | 0 | 0 | 460 |
| ctl-steady | public 1.1.1.1:443 | 1403 | 1400 | 1376 | 3 |
| ctl-steady | metadata 169.254.169.254:80 | 1491 | 1491 | 1466 | 0 |
| ctl-steady | node ssh | 1493 | 1493 | 1468 | 0 |
| ctl-steady | kubernetes api clusterip | 1493 | 1493 | 1468 | 0 |
| ctl-steady | gateway model port | 538 | 0 | 0 | 527 |
| ctl-steady | gateway admin port | 536 | 0 | 0 | 525 |
| exec-repro-steady | public 1.1.1.1:443 | 459 | 5 | 0 | 448 |
| exec-repro-steady | metadata 169.254.169.254:80 | 467 | 5 | 0 | 455 |
| exec-repro-steady | node ssh | 472 | 5 | 0 | 459 |
| exec-repro-steady | kubernetes api clusterip | 457 | 6 | 1 | 445 |
| exec-repro-steady | gateway model port | 470 | 0 | 0 | 460 |
| exec-repro-steady | gateway admin port | 470 | 0 | 0 | 460 |
