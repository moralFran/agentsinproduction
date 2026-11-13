# Experiment 04 · network investigation on the cluster (2026-11-13)

> Raw files larger than about 150 KB are stored compressed: a file this report names as `x.log` or `x.txt` may be
> `x.log.gz` / `x.txt.gz` in the folder (same content, `gzip -d` restores it).

A third cluster session, about the two network findings of the integration rounds of 2026-11-12
(`../integration-2026-11-12/`, `../integration-2026-11-12-followup/`): the start-up window of a new pod, and the rare
single connections that seemed to pass a policy that had long been applied. **Nothing here is experiment data and no
archived record was written.** No provider key was on the machine: the gateway ran with a dummy key and its log has no
forwarded call.

**Corrected after an external review (second session, 11:50 to 12:02Z; section "Correction after review" below).** The
script that matched accepted packets to probe tries joined on source address and port only. It now joins on address,
port, destination and time. The second headline stands: **0 accepted SYNs unexplained or ambiguous among 928,346**; five
packets moved from "allowed" to "start-up window", and five late events turned out to have no trace at all (they fall
in the two minutes when no trace reader was running). The same session checked two harness fixes live and reinstalled
k3s and Kata on the same VM with guest seccomp and the gate (sections "Review follow-up" at the end).

**Time limit.** The owner capped the machine at 2 hours from creation (08:31Z), so the samples are smaller than first
planned: about 15 pods per kind and arm for start-up, one 10-minute block without churn and one 16-minute block with
churn for steady state, 5 repetitions per runtime for the apply latency. Every rate below carries its denominator.
A different policy enforcer (to tell whether the window is specific to k3s's controller) was **not run**.

## Short answers

1. **Start-up window: reproduced, cause seen at rule level.** Until k3s's policy controller has written the pod's
   rules, packets from the new pod's address match no pod chain and are accepted. The window ends with the controller's
   rule restore. It is not "0.3 to 0.7 s": it was 0.6 to 0.8 s for quiet Kata pods, 0.4 to 1.6 s for Kata pods and 0.1 to
   1.1 s for runc pods while other pods were being created, and under 20 ms for quiet runc pods.
2. **Late connections through an applied policy: none.** The probe did report them again (in Kata pods only, about one
   in 3,600 forbidden tries, with or without churn, internal and external targets alike), but every one that could be
   looked up was **rejected by the node's firewall**: the packet trace shows the reject rule of the pod's chain, no
   connection-tracking entry was created, no SYN-ACK went to the pod, and the socket was not connected (state CLOSE or
   SYN_SENT, `ECONNREFUSED` pending). They are **false successes of `connect()` inside the Kata guest**, not leaks.
   The events of 2026-11-12 were recorded by probes that kept nothing but "connect() returned"; they cannot be
   re-examined, but they have the same signature (Kata pods only, single tries).
3. **New, not asked for:** the Kata guest itself opens TCP connections to public time servers (port 4460) from the
   pod's address as soon as the VM boots. Before the pod's rules exist they pass (56 seen, 41 of them before the
   container's first process); once the rules exist they are rejected (689 seen). No runc pod sent any.
4. **The init-container gate works:** 0 of 60 gated pods saw an established forbidden connection from the main
   container, against 39 of 60 ungated Kata pods in the same minutes. It costs about 8 s per pod as configured,
   4 to 5 s with shorter timings (8 pods).
5. **Guest seccomp:** one chart value (`shims.qemu.dropIn`) makes `Seccomp: 2` appear in every pod kind; the Go case
   still reproduces 3/3 and 3/3.
6. **PATH:** `/etc/profile` of the image resets `PATH` for login shells; `bash -o pipefail -c` keeps `go`.
7. **Gateway confirmation patch (T7): checks A, B, C and D pass.**

## What was run

Harness: public commit `57dc8eb`, copied with `git archive`; from 09:19Z plus the four files of the uncommitted patch
(T7), and from 08:55Z `cases/pod.py` / `cases/prep.py` with the gate (built into pods only where the plan says "gate").
Scripts of this round: `controls/`. Raw files: `raw/` (identifiers replaced: `<project>`, `/home/lab`; public
addresses other than the probe's own targets replaced by `<public-ip>`; in two randomly generated chain names four
letters that happened to spell an unrelated name were changed, the fourth to a lower-case `x`). Tables computed from
`raw/`: `analysis-main.md` (`controls/analyze.py`) and `extra-checks-main.txt` (`controls/extra-checks.py`).

| When (UTC) | What |
|---|---|
| 08:31:27 | VM created by the owner (empty; n2-standard-8, Ubuntu 24.04) |
| 08:36:39 to 08:40:38 | T0: `install-docker.sh`, `install-k3s-kata.sh`, `build-images.sh`, `setup-lab.sh` (dummy key), `new-run.sh` (`raw/setup/`) |
| 08:41:27 | k3s restarted with `v: 2` (controller log), kubelet log size raised, journald rate limit off |
| 08:42:11 to 08:47:50 | gobwas/ws prepared and reproduced with the unchanged harness (`raw/case/`) |
| 08:45 to 08:50 | pilots of the probe and the recorders (`raw/pilot/`) |
| 08:50:55 | recorders started (`controls/start-capture.sh`), then eight steady pods (process start 08:51:05) |
| 08:53:15 to 09:03:05 | **block without churn**: 2 controller syncs, 0 pod events outside `kube-system` |
| 09:03:15 to 09:19:00 | **block with churn**: 180-pod start-up batch (T1, T4), 10 apply-latency pods (T3), 4 more steady pods; 834 controller syncs, 194 distinct pods |
| 09:19:38 to 09:25:13 | T7 (redeploy, checks A to D) and, beside it, five pods of the raw-system-call probe (`raw/race/`) |
| 09:25:19 to 09:33:28 | T5: guest seccomp on, 8 pods, reproduction (`raw/t5/`) |
| 09:35 to 09:38 | 8 gated pods with shorter gate timings (`raw/t4tuned/`); TRACE rule removed from the raw table |

Software (`raw/setup/versions.txt`): k3s v1.37.2+k3s1; network policy controller **kube-router v2.11.1-k3s1, iptables
implementation** (`npc_iptables.go`; the build also contains an nftables one, not in use); host iptables v1.8.10 in
**nf_tables** mode (k3s bundles only `ipset`); kube-proxy in iptables mode; flannel with k3s's default backend; Kata 4.3.1 (`kata-qemu`,
guest kernel 6.18.56); host kernel 7.0.0-1017-gcp; containerd v2.3.7-k3s1.

### Instruments

- **Probe** (`controls/netwatch.py`, in the pod, built with the harness's own spec builders as on 2026-11-12): one
  thread per target, one TCP connect every 0.2 s (steady) or 0.1 s (start-up), every try logged with epoch
  milliseconds, target, result, duration and source port; the pod's address in the first line. Targets: public address
  443 (1.1.1.1), metadata endpoint, node address 22 and 6443 ("external"); Kubernetes API ClusterIP, gateway ClusterIP
  8080 and 8081, gateway pod 8080 and 8081, DNS pod 53 ("internal"). Destinations a pod's policy allows are tried
  once every 2 s only. Three versions: **v1** logs what `connect()` returned; **v2** (from 09:03Z) also reads the
  socket after a "success" (TCP state, `getpeername()`, `SO_ERROR`); **v3** (09:19Z) makes the system calls one by one.
  The connect timeout is 0.2 s: the controller rejects with ICMP, the node rate-limits ICMP errors, so most blocked
  tries end as timeouts (with the 1 s timeout of the earlier probes a blocked target gets about one try per second).
- **Controller log**: k3s `v: 2` in `/etc/rancher/k3s/config.yaml`. That is the flag that shows every sync: `Starting sync
  of iptables with version`, `Saving ... took`, `Restoring IPv4 ipset took`, `Restoring IPv4 iptables rules took`, `sync
  iptables took`, and `Received update to pod` (`raw/main/cap/k3s-journal-netpol.log.gz`, microsecond times).
- **Packet trace**: `iptables -t raw -I PREROUTING -s 10.42.0.0/16 -p tcp --syn -j TRACE`, read by `xtables-monitor
  --trace` and by `nft monitor trace` at the same time. `xtables-monitor` prints the rule text but stops whenever the
  netlink buffer overflows: it was restarted 4,827 times in the main block and loses lines each time
  (`controls/tracefilter.py` writes one summary line per packet with a time and keeps the full trace of packets with
  no drop line). `nft monitor trace` never stopped; its raw output (2.1 GB) stayed on the VM and was reduced there by
  `controls/nft-verdicts.py` and `controls/late-lookup.py`.
- **Connection tracking**: `conntrack -E` for pod sources (a SYN the firewall lets through creates a NEW event).
- **Rule snapshots**: filter table and ipsets every 0.5 s, diffs with time (`controls/rulewatch.py`).
- **Pod events** with the time received (`controls/podwatch.py`), and a pcap of SYN/RST/ICMP on `cni0` from 08:59Z
  (kept on the VM; the lines for each late event are in `raw/main/late-events.jsonl`).

Limits of the instruments: the trace was not running from 08:51:10 to 08:53:03 (`xtables-monitor` had stopped by
itself; the loops were started then), so the first seconds of the eight steady pods have conntrack events but no
trace. During table replacements both trace readers sometimes print a line "policy accept" for the base chain before
the rule lines of the same packet (6,391 of 928,346 SYNs in the nft trace); the FORWARD chain's policy on this node is
DROP and those packets go on to their reject rule, so a trace counts as passed only when its **last** filter line is
the accept. Why that line appears was not investigated. The TRACE rule and the recorders were present in every
block; nothing was measured without them.

## T1 + T2 · the start-up window

Batch of 180 pods (`raw/main/batch/`, plan `raw/main/plan-batch.json`), 15 of each kind in three arms that share
the same minutes, six at a time: Kata without the gate, Kata with the gate, runc without the gate. Each main container
probes for 16 s. "Connected" means the socket was ESTABLISHED (probe v2). Full table: `analysis-main.md`.

| Arm | Pod kind | Pods with an established forbidden connection | Forbidden tries established / all | Last one, ms after the process started (min / median / max) |
|---|---|---|---|---|
| Kata, no gate | agent | 12 of 15 | 876 / 13,273 | 702 / 1,101 / 1,501 |
| Kata, no gate | exec repro | 13 of 15 | 816 / 16,476 | 400 / 901 / 1,611 |
| Kata, no gate | prep | 14 of 15 | 664 / 13,219 | 701 / 1,151 / 1,401 |
| Kata, no gate | validation (test container) | 0 of 15 | 0 / 16,147 | - |
| runc, no gate | agent | 15 of 15 | 294 / 13,125 | 101 / 202 / 701 |
| runc, no gate | exec repro | 15 of 15 | 294 / 16,342 | 101 / 202 / 1,102 |
| runc, no gate | prep | 15 of 15 | 221 / 13,127 | 102 / 201 / 503 |
| runc, no gate | validation (test container) | 0 of 15 | 0 / 16,276 | - |

These pods started while the node was busy (load average about 25 on 8 vCPUs). Quiet starts: the steady Kata pods of
08:51Z were open until 600 to 609 ms, the runc ones until 5 to 18 ms; the pilot Kata pods until 705 and 801 ms. The three
Kata pods started at 09:03Z, in the first seconds of the batch, were open until 1.0 to 1.8 s (a runc pod: 0.2 s).
The validation test container starts after the harness's own init container and had no window in 30 of 30 pods; the
observation of 2026-11-12 that it reached the node's ssh port on its first try did **not** repeat (0 of 30).
No pod reached a forbidden target again after it was first blocked (0 established late connections in 180 pods).

**Cause, as observed.**
- The trace of the packets that passed: 226 of 226 complete traces of SYNs to the metadata endpoint or the node's ssh
  port from pods whose namespace had its policy from the start contain **no jump for the source address into a
  `KUBE-POD-FW-*` chain**; they run through `KUBE-ROUTER-FORWARD` / `KUBE-ROUTER-INPUT` without a match and are accepted
  by flannel's forward rule or the INPUT policy (`example-startup-trace.txt`; all of them in
  `raw/main/cap/trace/passed-traces.log.gz`). Sampled start-up connections: 40 of 40 have a conntrack NEW event, 37 of
  37 with a recorded socket state were ESTABLISHED, 37 of 37 inside the pcap have a SYN-ACK.
- The controller: each pod update starts a full sync (median 243 ms, up to 1.35 s under churn, 881 syncs in the
  capture); the pod's chain and its jump rules appear with that sync's `iptables-restore`. For 45 of 45 runc pods and
  28 of 39 Kata pods with a window, every target's change from connected to blocked brackets the end of one restore
  (within 60 ms; the probe tries each target every 0.1 s, slower once tries time out). For the other 11 Kata pods the
  bracket is wider than that tolerance; not looked at one by one.
- So the window is the time between the pod's first process and the end of the first sync that knows the pod's
  address. The chain names change at every sync (they include the sync's version) and the table is replaced in one
  restore; no packet was seen passing because of a replacement (see the next section).

Not determined: when exactly the controller first learns the address relative to the container start (the journal's
`Received update to pod` lines do not say which update carried the address), and whether another enforcer has the
same window (not run).

## T1 + T2 · late connections

### What the probes reported

Forbidden tries after each pod's first 5 s, inside the two blocks (12 steady pods; `analysis-main.md` has them per
pod and per target):

| Block | Runtime | Probe | Forbidden tries | `connect()` returned no error | of those ESTABLISHED |
|---|---|---|---|---|---|
| no churn | Kata (4 pods) | v1 | 106,214 | 33 (18 internal, 15 external) | not read by v1 |
| no churn | runc (4 pods) | v1 | 106,169 | 0 | - |
| churn | Kata (4 pods) | v1 | 170,104 | 43 (22 internal, 21 external) | not read by v1 |
| churn | runc (4 pods) | v1 | 170,120 | 0 | - |
| churn | Kata (3 pods) | v2 | 108,550 | 26 | **0** (26 of 26: state CLOSE, no peer, `SO_ERROR` 111) |
| churn | runc (1 pod) | v2 | 41,743 | 0 | 0 |
| 09:19 to 09:25 | Kata (3 pods) | v3 | 41,300 | 4 | **0** (4 of 4: state SYN_SENT, no peer, `SO_ERROR` 111) |
| 09:19 to 09:25 | runc (2 pods) | v3 | 29,495 | 0 | 0 |

Kata, v1: 76 in 276,318 tries (1 in about 3,600); 33 in 106,214 without churn and 43 in 170,104 with churn; 40 in
161,187 to internal targets and 36 in 115,131 to external ones. Every target had some (per-target list in
`analysis-main.md`). The "internal only" pattern of 2026-11-12 was chance. runc: 0 in 347,527 tries (all three probe versions); Kata, all versions: 426,168 tries.

### What the node did with those packets

`controls/late-lookup.py` took every try, in all pods of the main block, where `connect()` returned no error on a
forbidden target after that target had already been blocked in the pod: **133 tries, all in Kata pods**
(`raw/main/late-events.jsonl`, summary `raw/main/late-lookup-summary.txt`).

| Evidence for the same source address, port **and destination**, within 3 s (corrected join) | Result |
|---|---|
| xtables-monitor trace line found | 92 of 133: **92 blocked** (reject rule of the pod's `KUBE-POD-FW-*` chain), 0 passed |
| the 41 without one, in the nft trace (packet identified by its own pre-translation line and IP id) | 36 blocked, 0 passed, **5 not found** |
| conntrack NEW event | **0 of 133** |
| packets in the pcap (from 08:59Z) | 101 of 133: SYN-ACK to the pod **0**, ICMP port-unreachable to the pod 101 |
| socket after `connect()` (probe v2) | 47 of 47: state CLOSE, `getpeername()` fails, `SO_ERROR` = `ECONNREFUSED`; the other 86 are v1 tries |

So 128 of 133 are traced as rejected. The other 5 (steady pods, 08:51:38 to 08:52:48Z, v1 probe) fall in the gap
from 08:51:10 to 08:53:03Z when neither trace reader was running, and before the pcap: for them the only host-side
evidence is that conntrack, which was recording, has no NEW event. (The first version of this table said 132 and 1:
four of those five had been paired with the blocked packet of a later try that reused the port.)

The six-minute block with the v3 probe added 4 more (Kata), all blocked in the trace for the same destination, no
conntrack event, no SYN-ACK, 4 ICMP errors (`raw/race/`).

Independent of the probe's result, for the 12 steady pods after their first 5 s (`analysis-main.md`, "What the host
recorded"): conntrack NEW events to forbidden destinations **0** (to allowed ones 8,362); traced SYNs to forbidden
destinations 487,199 blocked, **0 passed**, 2,811 with an incomplete trace (reader restarts).
And for the whole main block from the nft trace (`raw/main/nft-verdicts-summary.txt`): 928,346 SYNs from pod
addresses, 905,702 dropped, 22,644 accepted. Each accepted SYN is matched to the probe try with the same source address,
source port and destination whose time is closest (within 1 s; the packet's time is its conntrack NEW event for 22,590,
its xtables-monitor line for 45, none for 9, which are matched on the three fields alone and each have tries of one
class only). Corrected classes (version 1 in brackets): 7,389 to allowed destinations (7,394), 3,301 in a start-up
window (3,298), 11,753 from the T3 pods before their policy existed (11,753), 117 to port 4460 from the Kata guest
before the pod's window closed (115), and 84 from gated pods to the gate's canaries before the main process started
(84). **Unexplained: 0. Ambiguous: 0.** No SYN to a probe target was accepted outside a window
(`raw/main/nft-verdicts-summary.txt`, `nft-verdicts-accepted.txt`, `nft-verdicts-examined.jsonl`, which is empty).
The v3 block (`raw/race/`): 60,925 SYNs, 113 accepted: 96 start-up, 12 allowed, and 5 to port 4460 from the address of
a pod that is not a probe pod: the validation pod of T7 check B (`ci-exec`, Kata), sent between 0.7 s before and 0.1 s
after the API first showed that pod's address (the Kata guest again); 0 unexplained.

### What the false success is

Probe v3 (`raw/race/pods/`) repeats what CPython's `socket.connect()` does on a socket with a timeout: non-blocking
`connect()`, `poll()` for POLLOUT|POLLERR, `getsockopt(SO_ERROR)`, success if that is 0.

| Runtime (kernel) | Tries that ended with an ICMP refusal | Normal: first `SO_ERROR` = 111 | Anomalous: `poll()` returned POLLERR only, first `SO_ERROR` = **0**, state SYN_SENT, next `SO_ERROR` = 111 |
|---|---|---|---|
| Kata guest (6.18.56) | 881 | 877 (816 with POLLOUT\|POLLERR\|POLLHUP, 61 with POLLERR only) | **4** |
| runc (host 7.0.0) | 594 | 594 (all POLLERR only) | 0 |

So in the guest, when the node's ICMP rejection arrives, `poll()` sometimes reports the socket ready while the first
read of `SO_ERROR` still returns 0, and Python's `connect()` returns as if connected. The error is there a moment
later and the socket never had a peer. The late "connections" line up with whole seconds after the process start
because the node sends at most one ICMP error per second per destination and only the tries that receive one can
show this. Which kernel code path produces the zero was **not determined** (no guest-kernel tracing was done); it
did not happen under runc in 594 refusals, which is too few to say it cannot.

### Sync, churn, address reuse

- The false successes happen with no sync nearby: the block without churn had 2 syncs (the periodic one, every
  5 minutes) and 33 of them; `analysis-main.md` lists each with the distance to the nearest sync and pod event.
- Real late leaks: none, with churn (834 syncs, 194 pods) or without.
- Address reuse: no pod address was used twice in the capture (0 of 208), so the stale-ipset hypothesis was
  **not tested**. The hypothesis of an instant without rules during a sync was tested by the trace: 0 SYNs passed
  outside a window in 834 syncs while about 487,000 forbidden SYNs from steady pods were being traced.

## The Kata guest's own traffic (found on the way)

SYNs to TCP port 4460 (the key-exchange port of secure NTP) appear from the addresses of 40 Kata pods and of no runc
pod. No probe uses that port; the destinations are public time servers (`<public-ip>` in the raw files). In the timed
trace summaries (`extra-checks-main.txt`): 752 such SYNs; **56 passed**, 41 of them before the container's process had
started and 15 inside the pod's start-up window; 689 were rejected (28 before the process started, 661 after the pod's
rules existed); 7 have an incomplete trace. The nft trace, which lost nothing, has 117 accepted SYNs to that port in the
main block: 78 before the container's process started and 39 inside the pod's start-up window, none later. So the guest's time service reaches the internet in the same window, from
pods of `ci-exec` and `ci-agent` too, and is cut off when the rules arrive. It is the Kata guest image's own service,
not case code; whether it then works without its time source, and how to turn it off, was **not investigated**.

## T3 · experiment 03's scenario (policy applied to a running pod)

`controls/t3-latency.sh`: a pod of the agent's shape in a namespace without a policy probes every 0.05 s; 8 s after
it is Running, experiment 03's policy is applied with `kubectl apply`. Five repetitions per runtime, all during the
churn block (`raw/main/t3lat/`); plus the two long pods of the steady blocks (`steady-t3-*`, applied at 08:51:29
with nothing else going on).

| | Last forbidden connection after `kubectl apply` **returned** | ...after it **started** | `kubectl apply` took |
|---|---|---|---|
| Kata, 5 repetitions (busy node) | -2, 58, 90, 95, 499 ms | 417 to 1,319 ms | 419 to 932 ms |
| runc, 5 repetitions (busy node) | 48, 255, 276, 395, 401 ms | 592 to 886 ms | 325 to 723 ms |
| Kata, quiet (1) | -101 ms | 56 ms | 157 ms |
| runc, quiet (1) | -48 ms | 109 ms | 157 ms |

In all 12 the policy was in force within 0.5 s of the command returning; experiment 03 waited 15 s.
Steady state of the two long pods after the apply: Kata 76,756 forbidden tries in the two blocks, 19 `connect()`
returns without error (v1 probe; 10 in the block without churn, 9 with churn); runc 76,741 tries, 0. Host side for
both pods: 0 conntrack NEW events, 0 traced SYNs passed, 114,726 blocked. Same false success as above, no leak.
Experiment 03 probed with `curl`; whether `curl` can show the same false success was not tested.

## T4 · the gate

`cases/pod.py` and `cases/prep.py` (diffs in `harness-changes/`) add an init container `netgate`: same image, same
container securityContext, no volume, no secret, no environment except its own settings and the node address. It
tries the forbidden canaries (public address 443, metadata endpoint 80, node address 10250, Kubernetes API ClusterIP;
for `ci-prep` the last three) every 0.25 s until none has connected in 8 consecutive rounds spanning at least 2 s;
agent pods then wait until the gateway's model port answers. After 60 s it exits 1 and the pod fails; `pod.py` prints
`"infra_error": "netgate: ..."` in its POD line and `prep.py` raises "infrastructure error, network gate". In
validation pods it runs after `validate-prepare` and immediately before the test container. `NETGATE=0` builds pods
without it. `infra/test_security.py` passes (43) with the change; the other suites were not re-run.

| Pod kind (Kata, 15 + 15 pods, same minutes) | With the gate: pods with an established forbidden connection in the main container's 16 s | Without | Gate passed | Gate saw a canary answer first |
|---|---|---|---|---|
| agent | **0 of 15** (0 of 12,971 tries) | 12 of 15 | 15 of 15 | 8 of 15 |
| exec repro | **0 of 15** (0 of 16,159) | 13 of 15 | 15 of 15 | 6 of 15 |
| prep | **0 of 15** (0 of 12,944) | 14 of 15 | 15 of 15 | 5 of 15 |
| validation | 0 of 15 (0 of 16,142) | 0 of 15 | 15 of 15 | 0 of 15 |

Cost, from `kubectl apply` returning to the main container's first instruction: busy node (batch, medians of 15)
14.2 to 14.3 s with the gate against 5.4 to 6.3 s without for agent, exec and prep, 21.0 against 12.7 s for
validation; quiet node (one pod each, `raw/t5/pods/`) 11.8 to 11.9 s against 3.6 to 3.8 s, validation 13.7 against
7.5 s. The gate's own wait was 4.8 to 5.6 s (median, max 6.3 s): each round waits out a 0.5 s connect timeout because
most rejections arrive as nothing at all (ICMP rate limit). The rest is one more container in the sandbox.
With a 0.2 s connect timeout and a 0.1 s interval (`NETGATE_CONNECT_TIMEOUT`, `NETGATE_INTERVAL`; same 8 rounds over
at least 2 s), 8 pods on a quiet node, one at a time (`raw/t4tuned/`): gate wait 2.2 to 2.4 s, start 7.9 to 8.8 s for
agent, exec and prep (against 3.6 to 3.8 s without a gate) and 10.7 and 11.7 s for validation (against 7.5 s); 0 of 8
main containers saw a forbidden destination (0 of 3,952 tries). The defaults in `pod.py` are still the ones the 60-pod
batch ran with.

What the gate does not do: it shows the rules were in force when it looked. It cannot prevent a later lapse; this
round found no later lapse to prevent. It does not stop the Kata guest's own connections before the rules exist
(section above), and its canaries are fixed addresses: where a canary does not exist (no metadata endpoint) that
check passes at once. A failed gate (timeout) was provoked in the second session (B1 below). The gate was exercised
through the real harness path once: the reproduction of T5 ran with it in all four pods.

## T5 · seccomp inside the Kata guest

Kata's `configuration-qemu.toml` has `disable_guest_seccomp = true` (line 627); the pinned chart installs with a
one-shot job (`deploymentMode: job`), not a daemon, and offers `shims.<shim>.dropIn`, which kata-deploy writes as
`config.d/50-user-overrides.toml` beside the shim's configuration. `infra/install-k3s-kata.sh` now passes

    shims: {qemu: {dropIn: "[runtime]\ndisable_guest_seccomp = false\n"}}

On this VM it was applied with `helm upgrade --reuse-values -f` (`controls/t5-seccomp.sh`, `raw/t5/00-enable-guest-seccomp.log`):
kata-deploy ran again (51 s), the drop-in appeared, `configuration-qemu.toml` stayed byte-identical.
- `/proc/self/status` in 8 of 8 new Kata pods (agent, exec repro, prep, validation; with and without the gate):
  `Seccomp: 2`, `Seccomp_filters: 1`, `NoNewPrivs: 1`. Before the change every Kata pod of this round showed
  `Seccomp: 0` (all Kata pods of the batch and the steady blocks); runc pods showed 2 / 1 before it.
- Reproduction of gobwas/ws with guest seccomp on (and the gate): **reproduced, broken failed 3 of 3, fixed passed
  3 of 3**, integrity control clean, cache control passes (`raw/t5/repro.log`, `repro-seccomp.jsonl`).
- Start time: no change visible (quiet, one pod each: 3.6 to 3.8 s after the change; the pilot before it, four pods
  at once, 4.6 to 5.4 s). One pod per kind; not a measurement of small differences.

Not done: the new `helm install` line from an empty machine (in the first session only the upgrade path ran; in the
second it ran after uninstalling k3s and removing `/opt/kata` on the same VM, section C below); a hand edit of
`configuration-qemu.toml` to see whether a re-run overwrites it; any Python case under guest seccomp.

## T6 · why `bash -lc` loses Go

`raw/t7/D-shell-path.log`, in an agent pod built by `cases/pod.py`: the container's `PATH` starts with the case venv
and `/usr/local/go/bin`. A login shell sources `/etc/profile`, whose lines 4 to 9 set
`PATH="/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games"` for any non-root user and export it (there is no
`/etc/profile.d` file and no profile in `HOME=/tmp`). With `bash -lc`: `python3` and `git` resolve, `go: command not
found`. With `bash -o pipefail -c`: `/usr/local/go/bin/go`, `/usr/bin/python3`, `/usr/bin/git`, `go version go1.27.4`.

## T7 · the gateway confirms a `gateway_unavailable` claim

Files synced from the working tree (`raw/t7/00-redeploy.log` has their sha256 before and after and the sums of the
ConfigMaps): `gateway/gateway.py`, `cases/attempt.sh`, `agent/agent.py`, `executor/executor.py`; redeployed with
`infra/setup-lab.sh` and the dummy key. Pods of these checks were built without the gate (`NETGATE=0`), since the
change under test is the gateway's. `controls/t7-checks.sh`; outputs in `raw/t7/`.

- **A, confirmed claim: as expected, twice.** Run closed from the host right after it opened (that reply:
  `model_path_failures: 0`); the pod got 403 and reported `gateway_unavailable`; attempt.sh's own close then returned
  `model_path_failures: 1`; exit status 1; one infra line per try with reason "the gateway booked 1 failed call(s) to
  the run" and `gateway.model_path_failures: 1`; no journal file; the second invocation opened `...-r1-t2`.
- **B, unconfirmed claim: as expected.** VM-only `attempt-b.sh` (the only difference: `GATEWAY_URL` port 8081). The
  pod reported `gateway_unavailable` (`APIConnectionError: Connection error.`) after 1.3 s of agent time (pod 20.2 s
  wall, script 35 s with the validation); the close returned `model_path_failures: 0`; exit status 0 and "recorded as
  an attempt (error)"; one journal row with `agent.outcome: "error"`, `claimed_outcome: "gateway_unavailable"`,
  executor outcome `no_patch`; stored diff 0 bytes; no infra file; the same case and repetition again printed
  "already recorded; skipping". The start-up window did not show in this one try: the connection was refused. The
  gateway's ports are also guarded by the gateway's own ingress policy, which exists before the agent pod does: no
  probe pod of this round reached port 8080 or 8081 during its window.
- **C, `safe.directory` by path: works.** Reproduction with the new `executor.py`: reproduced (3 of 3 and 3 of 3),
  integrity control `clean`, six samples `sampled`, cache control passes; 0 lines with "git status failed" or
  "dubious ownership" in the four pod logs.
- **D, `bash -c`:** see T6.
- **No forwarded call:** 0 lines with `"verdict": "forwarded"` in the gateway log (the only verdicts: 2 `refused`);
  state at the end `spent_usd: 0.0, requests: 0, halted: null` (`raw/t7/no-forwarded-call.txt`, `gateway.log`).

## What can be stated

Supported by this round:
- "A new pod can reach what its namespace's NetworkPolicy forbids until the policy controller has written the pod's
  rules; on this cluster that took 0.6 to 0.8 s for a Kata pod on a quiet node and up to 1.6 s on a busy one (39 of 45
  Kata pods without an init container, 45 of 45 runc pods)." Not "0.3 to 0.7 s", and not Kata-specific: runc pods have
  the window too, shorter.
- "The cause is the order of events: the pod's network works before the controller's next sync has added the pod's
  chain; packets in that time match no pod rule." Seen in the trace and the controller log.
- "A container that starts after an init container had no window" (30 of 30 validation test containers, 60 of 60
  gated pods).
- "Once the rules were there, nothing got through: in about 774,000 forbidden tries from long-running pods (426,168
  Kata, 347,527 runc) the node let no connection pass, and of 928,346 traced SYNs none was accepted outside a start-up
  window, with 834 controller syncs and 194 pods coming and going."
- "The single late connections reported on 2026-11-12 are, on this evidence, a probe artifact in Kata guests:
  `connect()` returned success for a connection the node had rejected." With the limit that those earlier events
  themselves cannot be re-examined.
- "With an init container that waits for the policy, the main container saw no forbidden destination (0 of 60)."
- "The Kata guest opens connections of its own (time service) from the pod's address before the rules exist."

Not supported:
- That the cause of the late connections is the controller re-syncing, or stale ipset entries. No real late
  connection exists in this data; the re-sync idea was tested and not seen, the ipset idea could not be tested.
- That the node "answers 401 on the admin port" for those late tries: nothing was ever connected.
- Any statement about another CNI or policy enforcer, or about k3s's nftables implementation: not run.
- A kernel-level explanation of the false success, or that it cannot happen under runc.
- That the window has a fixed upper bound: the largest seen was 1.8 s, on a node at load 25; nothing bounds it.
- Small differences in start time from guest seccomp (one pod per kind).

## Not run

- T8, another policy enforcer: cancelled with the time limit.
- Steady state of 30 minutes per condition, 30 pods per kind, 10 apply repetitions: reduced as stated.
- The gate inside a complete round (`run-round.sh`, `validate.py`). (Its timeout path: run in the second session, B1.)
- A block without the TRACE rule and recorders, to see whether they change the window.

## Correction after review (classifier join)

**The defect.** `controls/nft-verdicts.py` (version 1, kept as `controls/nft-verdicts-v1.py`) matched an accepted SYN to
probe tries by source address and source port only, and any "allowed" try with that pair made the SYN "allowed"
(then "start-up", then "pre-policy"). A pod reuses source ports for other destinations, so an accepted SYN to a
forbidden destination could inherit another try's class, and a real late connection could have been hidden the same
way. `late-lookup.py` and the per-event lines of `analyze.py` had the same weak join (address and port within 3 s,
any destination). `extra-checks.py` part 1 and the count of start-up traces do not join on ports.

**The fix** (`controls/nft-verdicts.py` version 2; its header says the rules):
- the join is on source address, source port **and destination** (the destination before Service translation, from
  the packet's own PREROUTING trace line) **and time**: the try closest in time among those with the same three fields,
  within 1 s. The nft trace has no times; a packet's time is the conntrack NEW event of the same three fields (the n-th
  accepted SYN of a key with the n-th event, only when the counts are equal), else its xtables-monitor summary line,
  else none;
- a doubt is never resolved towards "allowed": tries of different classes that time cannot separate are AMBIGUOUS; a
  SYN with no try for its destination is explained only by a rule that uses its time (guest port 4460 before the
  pod's window closed; a gate canary before the main process started), else UNEXPLAINED; each such SYN is written to
  `nft-verdicts-examined.jsonl` with conntrack, pcap and probe evidence;
- `controls/test_nft_verdicts.py`: a port reused for an allowed try and then for a late forbidden try whose SYN is
  accepted must come out UNEXPLAINED (it does; version 1 said "allowed"); the same with the SYN dropped gives nothing
  unexplained; the same without packet times is still UNEXPLAINED; a port reused for the same forbidden destination,
  once in the window and once late, gives one start-up and one UNEXPLAINED with times and two AMBIGUOUS without. Five
  of five pass, on the Mac and on the VM (`review-followup/a/test_nft_verdicts.out`);
- `late-lookup.py` (version 1 kept as `late-lookup-v1.py`) requires the destination for the trace line, the conntrack
  event and the nft trace; `analyze.py` (`analyze-v1.py`) quotes trace and conntrack lines only for the same
  destination within 3 s, and reads the compressed probe logs and pod events of this folder (as published after the
  first session it could no longer find the steady pods' logs, which had been compressed); the count of start-up traces
  is now a script (`controls/startup-traces.py`).

**Recomputed on the VM from the raw trace** (old outputs kept with the suffix `-v1` beside the new ones in `raw/main/`
and `raw/race/`; `analysis-main-v1.md`, `extra-checks-main-v1.txt`):

| Number | First report | Corrected |
|---|---|---|
| SYNs at the filter table / dropped / accepted | 928,346 / 905,702 / 22,644 | same |
| accepted: allowed | 7,394 | **7,389** |
| accepted: start-up window | 3,298 | **3,301** |
| accepted: T3 pods before their policy | 11,753 | 11,753 |
| accepted: guest port 4460 | 115 | **117** (78 before the container's process started, 39 inside the window) |
| accepted: gate canaries | 84 | 84 (all before the gated pod's main process started) |
| accepted: unexplained / ambiguous | 0 (weak join) | **0 / 0** |
| late events traced as rejected | 132 of 133 (1 not found) | **128 of 133** (5 not found: no trace reader was running) |
| late events with a conntrack NEW event / a SYN-ACK in the pcap | 0 of 133 / 0 of 101 | same |
| complete passed start-up traces without a jump for the source address | 226 of 226 | same (`startup-traces.py`) |
| port 4460 in the timed xtables-monitor summaries | 752: 56 passed, 689 blocked, 7 incomplete | same |
| tables of `analysis-main.md` | | identical; only the per-event trace and conntrack lines changed |
| v3 block | 4 late events, all blocked | same; 113 accepted SYNs: 96 start-up, 12 allowed, 5 guest port 4460 from a T7 validation pod |

**The reclassified SYNs** (`review-followup/a/reclassified.txt`). Five that version 1 called "allowed" because the pod
later or earlier used the same source port for an allowed destination; all five are start-up-window connections
(conntrack NEW event within 0.2 s of a probe try with the same three fields that connected, socket ESTABLISHED, before
that target was first blocked in the pod):
- `10.42.0.37:38760` to `169.254.169.254:80` and `10.42.0.37:51540` to `10.43.0.1:443` (`steady2-agent-kata`, 09:03:20 to 21Z)
- `10.42.0.38:36386` to `10.128.0.8:22` and `10.42.0.38:33326` to `169.254.169.254:80` (`steady2-prep-kata`, 09:03:21 to 22Z)
- `10.42.0.130:40728` to `10.128.0.8:6443` (`b-prep-rn-07`, 09:10:10Z)

Two more changed class: `10.42.0.137:53024` and `10.42.0.140:57746` to port 4460 of a public time server, "start-up" in
version 1 by the same accident, now "guest port 4460" (one before the container's process started, one inside the
window). Whether these five are the reviewer's five was not checked against the review; they are the only SYNs whose
class left "allowed".

**What this does and does not change.** No accepted SYN is unexplained or ambiguous, so the statement "no connection
passed the applied policy" stands on the stronger join. It is weaker than first written in one place: for 5 of the 133
late events there is no packet trace, only the absence of a conntrack entry. The guest clocks differ from the node's
by up to about 0.2 s in these logs, which is why the tolerance is 1 s and not a few milliseconds; no key had two tries
of different classes within it.

## Review follow-up B · two harness fixes, live (second session)

Files synced from the working tree: `cases/attempt.sh`, `cases/validate.py`, `gateway/gateway.py` (`cases/pod.py` and
`cases/prep.py` as committed); redeployed with `infra/setup-lab.sh` and the dummy key
(`review-followup/b/00-redeploy.log`). After the VM restart k3s had registered a second node object under the short
host name, as on 2026-11-12; k3s was restarted and the stray object deleted before anything ran.
Script `review-followup/controls/b-checks.sh`, SMOKE rounds, nothing is data.

- **B1, the gate fails for an agent pod: pass.** `NETGATE_PUBLIC` pointed at the gateway's model port (allowed for agent
  pods, so never refused) and `NETGATE_DEADLINE=8`. `attempt.sh` printed "the agent's pod did not start (netgate:
  {"ok": false, "why": "a forbidden destination still answers", ...})", exit status 1; one infra line whose reason
  carries the gate's JSON; no journal file; the run closed at the gateway with `spent_usd: 0.0, calls: 0,
  model_path_failures: 0`; the second invocation opened `...-r1-t2` and ended the same way (`B1-gate-failure.log`,
  `B1-infra-smoke-gatefail.jsonl`).
- **B2, run closed before the pod's first call: pass.** attempt.sh's close returned `model_path_failures: 1,
  model_path_failure_reasons: {"run_closed": 1}`; exit status 1; the infra line carries both; no journal
  (`B2-run-closed.log`, `B2-infra-smoke-gwconf2.jsonl`).
- **B3, a valid token with a forbidden request: pass.** From the host: a run opened; a request with `"stream": true`
  and an unknown field got 403 "field not allowed"; a request with a model outside the price list got 403 "model not
  allowed"; the close replied `model_path_failures: 0` with no reasons. Control: the same token after the close got 403
  and that one was booked (`model_path_failures: 1, {"run_closed": 1}`) (`B3-valid-token-forbidden-request.log`).
- **No forwarded call:** 0 lines with `"verdict": "forwarded"`; 4 `refused`; gateway state `spent_usd: 0.0, requests: 0`
  (`no-forwarded-call.txt`, `gateway.log`).

Not checked live: the other reason codes (gateway_halted, state_write_failed, total_budget, upstream_error,
provider_<status>) and the order of the run cap and the total cap; they need a forwarded or failing upstream call.

## Review follow-up C · reinstall with guest seccomp and the gate (second session)

**Not an empty machine.** On the same VM: `k3s-uninstall.sh` (6 s; `/var/lib/rancher` gone), `/opt/kata` removed, then
`infra/install-k3s-kata.sh` of the working tree as it is (2 min 7 s, exit 0: first run of its `helm install ... -f
<values>` line), `infra/build-images.sh` (the box image again, from Docker's cache), `infra/setup-lab.sh` with the
dummy key, and one gated Kata pod of each kind. Docker, Helm, `/srv/ci` with the prepared case and the run folder were
there from before. `review-followup/controls/c-reinstall.sh`; logs in `review-followup/c/` (in the uninstall script's own
trace one distribution name in a test expression is replaced by a placeholder).

- Drop-in: `runtimes/qemu/config.d/50-user-overrides.toml` present after the install (helm revision 1), content
  `[runtime]` / `disable_guest_seccomp = false`; the base file still says `true` on line 627 (`03-drop-in.txt`).
- Four pods (agent, exec repro, prep, validation; `07-pods-summary.txt`): `Seccomp: 2`, `Seccomp_filters: 1` in 4 of 4;
  gate `{"ok": true, "why": "policy in force"}` in 4 of 4 (waited 4.8 to 5.3 s); 0 established forbidden connections
  from the main containers.
- From uninstall to the last pod: 3 min 45 s (11:57:47 to 12:01:32Z).

Not done here: a reproduction or any case code after the reinstall; the k3s extra verbosity of the first session is
gone with the uninstall (default configuration now).

## Harness changes of this round (uncommitted, in the working tree)

`harness-changes/pod.py.diff`, `prep.py.diff`, `install-k3s-kata.sh.diff` (`git diff` against `57dc8eb`). No other
harness file was edited by this round. On the VM, T7 added the four files listed above.

## State of the VM

`aip-ci-01` was left running; it was neither stopped nor deleted by this round and no other cloud resource was
touched. On it: k3s (with `v: 2`), Kata with guest seccomp on (helm revision 2), the gateway with the dummy key and
the T7 `gateway.py`, the run folder with the T7 files, the gated `pod.py` / `prep.py` and a VM-only `attempt-b.sh`,
one prepared case (gobwas/ws), no probe pod, the raw traces and pcaps of this round (about 4 GB, not copied).
Time on: created 08:31:27Z; the last command of the first session ran at 09:38Z (1.2 h at 09:45Z); stopped by the owner
at 10:30Z.

Second session: started by the owner at 11:50Z, last command at about 12:03Z, stopped from outside at 12:30Z. State
left by it: k3s and Kata freshly reinstalled (default k3s configuration, guest seccomp drop-in from the install), the
lab namespaces and the gateway with the dummy key and the working tree's `gateway.py`, no probe pod; the raw traces
and pcaps of the first session still on its disk.
