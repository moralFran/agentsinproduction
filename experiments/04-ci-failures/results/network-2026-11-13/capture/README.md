# Helpers of the terminal captures of 2026-11-13

Small scripts that the channel's terminal captures of 2026-11-13 call (the captures type a command and run it for
real; these scripts start one pod or print compact lines from a real result). The capture definitions and casts live
with the video, not here.

| File | Runs | What it does |
|---|---|---|
| `probe.py` | inside a pod | one row per round of four connection tries to forbidden destinations: OPEN / refused / no answer |
| `newpod.py`, `probe-new-pod`, `idle-new-pod`, `watch-new-pod` | lab VM | start ONE pod built by `cases/pod.py build_spec` with only the main command replaced (probe, sleep, or a 15 s probe with the pod's clock in a namespace without a policy); `NETGATE=0` builds it without the gate |
| `show-gate` | lab VM | prints the fields of the gate's NETGATE result line |
| `show-kata-dropin` | lab VM | the base line and the drop-in file behind guest seccomp |
| `prepare-open-namespace`, `exp03-policy.yaml`, `rows-around-change` | lab VM | the policy-applied-afterwards scenario: an empty namespace, experiment 03's policy, and a filter that prints the rows around the change |
| `seccomp-before.py` | results folder | counts saved probe logs by runtime and Seccomp value, before and after the drop-in |
| `trace-excerpt.py` | results folder | filter-table lines of one passed and one rejected SYN of the same pod, cut from the recorded trace |
| `tally.py` | results folder | gate comparison of the start-up batch and the steady-state count |
