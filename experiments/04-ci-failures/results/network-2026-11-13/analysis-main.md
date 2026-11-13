controller syncs in the journal: 881; duration ms min/median/max: 74/243/1353
window 'no churn' 08:53:15.000Z to 09:03:05.000Z: 2 syncs, 0 pod events outside kube-system, 0 distinct pods
window 'churn' 09:03:15.000Z to 09:19:00.000Z: 834 syncs, 2030 pod events outside kube-system, 194 distinct pods

## Steady state

Probe v1 (the eight pods named steady-*) recorded only that connect() returned without an error; probe v2 (steady2-*) also read the
socket: 'established' = TCP state ESTABLISHED with a peer, 'false success' = connect() returned no error but the socket was CLOSE with ECONNREFUSED pending.

| Window | Pod | Probe | Runtime | Target class | Forbidden tries | connect() returned no error, socket not read (v1) | established (v2) | false success (v2) |
|---|---|---|---|---|---|---|---|---|
| no churn | steady-agent-kata | v1 | kata | internal | 11803 | 2 | - | - |
| no churn | steady-agent-kata | v1 | kata | external | 11801 | 6 | - | - |
| no churn | steady-agent-runc | v1 | runc | internal | 11799 | 0 | - | - |
| no churn | steady-agent-runc | v1 | runc | external | 11800 | 0 | - | - |
| no churn | steady-exec-kata | v1 | kata | internal | 17700 | 5 | - | - |
| no churn | steady-exec-kata | v1 | kata | external | 11800 | 1 | - | - |
| no churn | steady-exec-runc | v1 | runc | internal | 17696 | 0 | - | - |
| no churn | steady-exec-runc | v1 | runc | external | 11790 | 0 | - | - |
| no churn | steady-prep-kata | v1 | kata | internal | 14753 | 4 | - | - |
| no churn | steady-prep-kata | v1 | kata | external | 8851 | 5 | - | - |
| no churn | steady-prep-runc | v1 | runc | internal | 14747 | 0 | - | - |
| no churn | steady-prep-runc | v1 | runc | external | 8847 | 0 | - | - |
| no churn | steady-t3-kata | v1 | kata | internal | 17703 | 7 | - | - |
| no churn | steady-t3-kata | v1 | kata | external | 11803 | 3 | - | - |
| no churn | steady-t3-runc | v1 | runc | internal | 17697 | 0 | - | - |
| no churn | steady-t3-runc | v1 | runc | external | 11793 | 0 | - | - |
| churn | steady-agent-kata | v1 | kata | internal | 18900 | 1 | - | - |
| churn | steady-agent-kata | v1 | kata | external | 18900 | 9 | - | - |
| churn | steady-agent-runc | v1 | runc | internal | 18900 | 0 | - | - |
| churn | steady-agent-runc | v1 | runc | external | 18900 | 0 | - | - |
| churn | steady-exec-kata | v1 | kata | internal | 28350 | 8 | - | - |
| churn | steady-exec-kata | v1 | kata | external | 18900 | 2 | - | - |
| churn | steady-exec-runc | v1 | runc | internal | 28350 | 0 | - | - |
| churn | steady-exec-runc | v1 | runc | external | 18912 | 0 | - | - |
| churn | steady-prep-kata | v1 | kata | internal | 23627 | 9 | - | - |
| churn | steady-prep-kata | v1 | kata | external | 14177 | 5 | - | - |
| churn | steady-prep-runc | v1 | runc | internal | 23631 | 0 | - | - |
| churn | steady-prep-runc | v1 | runc | external | 14176 | 0 | - | - |
| churn | steady-t3-kata | v1 | kata | internal | 28351 | 4 | - | - |
| churn | steady-t3-kata | v1 | kata | external | 18899 | 5 | - | - |
| churn | steady-t3-runc | v1 | runc | internal | 28346 | 0 | - | - |
| churn | steady-t3-runc | v1 | runc | external | 18905 | 0 | - | - |
| churn | steady2-agent-kata | v2 | kata | internal | 16700 | - | 0 | 2 |
| churn | steady2-agent-kata | v2 | kata | external | 16700 | - | 0 | 3 |
| churn | steady2-exec-kata | v2 | kata | internal | 25050 | - | 0 | 7 |
| churn | steady2-exec-kata | v2 | kata | external | 16700 | - | 0 | 4 |
| churn | steady2-exec-runc | v2 | runc | internal | 25044 | - | 0 | 0 |
| churn | steady2-exec-runc | v2 | runc | external | 16699 | - | 0 | 0 |
| churn | steady2-prep-kata | v2 | kata | internal | 20875 | - | 0 | 6 |
| churn | steady2-prep-kata | v2 | kata | external | 12525 | - | 0 | 4 |

| Window | Runtime | Probe | Target class | Forbidden tries | connect() returned no error (v1) | established (v2) | false success (v2) |
|---|---|---|---|---|---|---|---|
| churn | kata | v1 | external | 70876 | 21 | - | - |
| churn | kata | v1 | internal | 99228 | 22 | - | - |
| churn | kata | v2 | external | 45925 | - | 0 | 11 |
| churn | kata | v2 | internal | 62625 | - | 0 | 15 |
| churn | runc | v1 | external | 70893 | 0 | - | - |
| churn | runc | v1 | internal | 99227 | 0 | - | - |
| churn | runc | v2 | external | 16699 | - | 0 | 0 |
| churn | runc | v2 | internal | 25044 | - | 0 | 0 |
| no churn | kata | v1 | external | 44255 | 15 | - | - |
| no churn | kata | v1 | internal | 61959 | 18 | - | - |
| no churn | runc | v1 | external | 44230 | 0 | - | - |
| no churn | runc | v1 | internal | 61939 | 0 | - | - |

Per target, both windows, all steady pods (forbidden tries / connected):
- churn: api (internal) 54500 / 7
- churn: dns (internal) 40867 / 0
- churn: gwa (internal) 54503 / 5
- churn: gwm (internal) 40873 / 3
- churn: gwpa (internal) 54504 / 5
- churn: gwpm (internal) 40877 / 2
- churn: meta (external) 54501 / 9
- churn: node22 (external) 54503 / 3
- churn: node6443 (external) 54514 / 4
- churn: pub (external) 40875 / 5
- no churn: api (internal) 23602 / 1
- no churn: dns (internal) 17703 / 5
- no churn: gwa (internal) 23596 / 6
- no churn: gwm (internal) 17701 / 2
- no churn: gwpa (internal) 23599 / 2
- no churn: gwpm (internal) 17697 / 2
- no churn: meta (external) 23601 / 2
- no churn: node22 (external) 23599 / 4
- no churn: node6443 (external) 23589 / 6
- no churn: pub (external) 17696 / 3

### Late connections in the steady pods (connect() returned no error on a forbidden target after it had been blocked in that pod; v2 pods: only tries whose socket was ESTABLISHED)

- 08:55:28.739Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node22` 10.128.0.8:22 (external), source port 51052, 263.09 s after the process started
  - controller: 232812 ms after the end of the previous sync, 67092 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:55:57.740Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `pub` 1.1.1.1:443 (external), source port 43404, 292.10 s after the process started
  - controller: 261813 ms after the end of the previous sync, 38091 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:58:20.848Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `dns` 10.42.0.8:53 (internal), source port 58198, 435.20 s after the process started
  - controller: 104920 ms after the end of the previous sync, 194982 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:59:29.739Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node22` 10.128.0.8:22 (external), source port 41366, 504.09 s after the process started
  - controller: 173811 ms after the end of the previous sync, 126091 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:12.739Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node6443` 10.128.0.8:6443 (external), source port 58464, 667.09 s after the process started
  - controller: 36803 ms after the end of the previous sync, 60094 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:14.848Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node22` 10.128.0.8:22 (external), source port 36246, 669.20 s after the process started
  - controller: 38912 ms after the end of the previous sync, 57985 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:18.746Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `gwa` 10.43.210.10:8081 (internal), source port 56312, 673.10 s after the process started
  - controller: 42810 ms after the end of the previous sync, 54087 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:47.739Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node6443` 10.128.0.8:6443 (external), source port 51846, 702.09 s after the process started
  - controller: 71803 ms after the end of the previous sync, 25094 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['P 1794560751534 10.42.0.29:51846 10.128.0.8:6443 10.128.0.8:6443 passed - 7']
  - conntrack: ['no NEW event recorded']
- 09:05:51.850Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `meta` 169.254.169.254:80 (external), source port 39132, 886.21 s after the process started
  - controller: inside a sync (243 ms after its start, 199 ms before its end)
  - pod events within 1 s: 3 pod(s) ['ci-agent/b-agent-kg-03', 'ci-agent/b-agent-rn-03', 'ci-exec/b-exec-rn-03']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:07:36.742Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `meta` 169.254.169.254:80 (external), source port 47090, 991.10 s after the process started
  - controller: 1018 ms after the end of the previous sync, 3283 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-exec-kg-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:08:45.849Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `meta` 169.254.169.254:80 (external), source port 40034, 1060.20 s after the process started
  - controller: 194 ms after the end of the previous sync, 1583 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-prep/b-prep-kg-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:09:32.852Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `pub` 1.1.1.1:443 (external), source port 60514, 1107.21 s after the process started
  - controller: inside a sync (197 ms after its start, 41 ms before its end)
  - pod events within 1 s: 5 pod(s) ['ci-exec/b-exec-kg-07', 'ci-exec/b-exec-kn-07', 'ci-exec/b-val-kg-06', 'ci-prep/b-prep-kn-06']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:11:12.741Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `gwpa` 10.42.0.13:8081 (internal), source port 55422, 1207.10 s after the process started
  - controller: 1996 ms after the end of the previous sync, 2803 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:12:38.739Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `pub` 1.1.1.1:443 (external), source port 50270, 1293.09 s after the process started
  - controller: 1463 ms after the end of the previous sync, 2105 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:12:46.848Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `pub` 1.1.1.1:443 (external), source port 48672, 1301.20 s after the process started
  - controller: 1793 ms after the end of the previous sync, 970 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-val-rn-09']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:14:47.848Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `meta` 169.254.169.254:80 (external), source port 56562, 1422.20 s after the process started
  - controller: 4019 ms after the end of the previous sync, 888 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-exec/b-val-kn-11', 'ci-exec/b-val-rn-11']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:14:57.851Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `node6443` 10.128.0.8:6443 (external), source port 41716, 1432.21 s after the process started
  - controller: 477 ms after the end of the previous sync, 1 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-agent/b-agent-kg-12', 'ci-agent/b-agent-rn-12', 'ci-exec/b-exec-rn-12', 'ci-exec/b-val-kg-11']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:17:52.849Z `steady-agent-kata` (agent, kata, 10.42.0.29) -> `meta` 169.254.169.254:80 (external), source port 45616, 1607.20 s after the process started
  - controller: 485 ms after the end of the previous sync, 1336 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/b-agent-kg-15', 'ci-exec/b-exec-kn-15']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:51:33.114Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwm` 10.43.210.10:8080 (internal), source port 53524, 28.03 s after the process started
  - controller: 3749 ms after the end of the previous sync, 2715 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:52:02.114Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `meta` 169.254.169.254:80 (external), source port 54298, 57.03 s after the process started
  - controller: 26187 ms after the end of the previous sync, 273717 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:52:13.110Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwpm` 10.42.0.13:8080 (internal), source port 45328, 68.03 s after the process started
  - controller: 37183 ms after the end of the previous sync, 262721 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-agent/steady-agent-runc']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:52:48.118Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `node22` 10.128.0.8:22 (external), source port 44986, 103.04 s after the process started
  - controller: 72191 ms after the end of the previous sync, 227713 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:04.127Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 46254, 119.05 s after the process started
  - controller: 88200 ms after the end of the previous sync, 211704 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:28.104Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwpm` 10.42.0.13:8080 (internal), source port 52206, 143.02 s after the process started
  - controller: 112177 ms after the end of the previous sync, 187727 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:35.102Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `dns` 10.42.0.8:53 (internal), source port 54028, 150.02 s after the process started
  - controller: 119175 ms after the end of the previous sync, 180729 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:48.103Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 47130, 163.02 s after the process started
  - controller: 132176 ms after the end of the previous sync, 167728 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:56:11.282Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 32850, 306.20 s after the process started
  - controller: 275355 ms after the end of the previous sync, 24549 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:56:12.282Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 32900, 307.20 s after the process started
  - controller: 276355 ms after the end of the previous sync, 23549 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:58:38.283Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `pub` 1.1.1.1:443 (external), source port 39488, 453.20 s after the process started
  - controller: 122355 ms after the end of the previous sync, 177547 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:03:34.287Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwpa` 10.42.0.13:8081 (internal), source port 38490, 749.21 s after the process started
  - controller: 62 ms after the end of the previous sync, 2829 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['t3k/t3lat-kata-1']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:06:19.184Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `pub` 1.1.1.1:443 (external), source port 53512, 914.10 s after the process started
  - controller: 1343 ms after the end of the previous sync, 18 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-agent/b-agent-kg-03', 'ci-exec/b-val-kg-03', 'ci-prep/b-prep-kn-03', 't3r/t3lat-runc-4']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:08:36.283Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `api` 10.43.0.1:443 (internal), source port 45490, 1051.20 s after the process started
  - controller: 29 ms after the end of the previous sync, 168 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-exec/b-exec-kg-06', 'ci-exec/b-exec-kn-06', 'ci-prep/b-prep-kn-05', 'ci-prep/b-prep-rn-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:10:14.183Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `meta` 169.254.169.254:80 (external), source port 57066, 1149.10 s after the process started
  - controller: 527 ms after the end of the previous sync, 1563 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/b-agent-kn-07', 'ci-prep/b-prep-kg-07']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:11:28.183Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 54372, 1223.10 s after the process started
  - controller: 92 ms after the end of the previous sync, 665 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-exec/b-val-kn-08', 'ci-exec/b-val-rn-08', 'ci-prep/b-prep-kn-08', 'ci-prep/b-prep-rn-08']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:11:33.212Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwm` 10.43.210.10:8080 (internal), source port 40276, 1228.13 s after the process started
  - controller: 1821 ms after the end of the previous sync, 2618 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:13:13.284Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwpm` 10.42.0.13:8080 (internal), source port 50146, 1328.20 s after the process started
  - controller: 4184 ms after the end of the previous sync, 1206 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-agent/b-agent-kn-10']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:14:36.214Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwa` 10.43.210.10:8081 (internal), source port 51822, 1411.13 s after the process started
  - controller: 984 ms after the end of the previous sync, 583 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-prep/b-prep-kg-11']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:16:20.287Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `gwpm` 10.42.0.13:8080 (internal), source port 41072, 1515.21 s after the process started
  - controller: 22 ms after the end of the previous sync, 647 ms before the next sync
  - pod events within 1 s: 3 pod(s) ['ci-agent/b-agent-kn-13', 'ci-exec/b-val-kg-13', 'ci-prep/b-prep-kg-13']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:18:58.283Z `steady-exec-kata` (exec-repro, kata, 10.42.0.28) -> `api` 10.43.0.1:443 (internal), source port 47818, 1673.20 s after the process started
  - controller: 2526 ms after the end of the previous sync, 6127 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:51:48.336Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node22` 10.128.0.8:22 (external), source port 35116, 42.01 s after the process started
  - controller: 12409 ms after the end of the previous sync, 287495 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:52:11.432Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node22` 10.128.0.8:22 (external), source port 41826, 65.10 s after the process started
  - controller: 35505 ms after the end of the previous sync, 264399 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:22.434Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node22` 10.128.0.8:22 (external), source port 53550, 136.10 s after the process started
  - controller: 106507 ms after the end of the previous sync, 193397 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:55:09.427Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwpa` 10.42.0.13:8081 (internal), source port 60736, 243.10 s after the process started
  - controller: 213500 ms after the end of the previous sync, 86404 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:57:37.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `meta` 169.254.169.254:80 (external), source port 36566, 391.20 s after the process started
  - controller: 61604 ms after the end of the previous sync, 238298 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:58:30.427Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node6443` 10.128.0.8:6443 (external), source port 53222, 444.10 s after the process started
  - controller: 114499 ms after the end of the previous sync, 185403 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:58:43.531Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwa` 10.43.210.10:8081 (internal), source port 33500, 457.20 s after the process started
  - controller: 127603 ms after the end of the previous sync, 172299 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:59:42.427Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node6443` 10.128.0.8:6443 (external), source port 35148, 516.10 s after the process started
  - controller: 186499 ms after the end of the previous sync, 113403 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:01:33.441Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwpa` 10.42.0.13:8081 (internal), source port 44902, 627.11 s after the process started
  - controller: 297513 ms after the end of the previous sync, 2389 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:41.427Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node6443` 10.128.0.8:6443 (external), source port 60538, 695.10 s after the process started
  - controller: 65491 ms after the end of the previous sync, 31406 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:02:45.439Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwm` 10.43.210.10:8080 (internal), source port 56364, 699.11 s after the process started
  - controller: 69503 ms after the end of the previous sync, 27394 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['1794560688.334438 NEW 1.1.1.1:443 reply-src 1.1.1.1']
- 09:04:53.535Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `meta` 169.254.169.254:80 (external), source port 43780, 827.21 s after the process started
  - controller: 473 ms after the end of the previous sync, 544 ms before the next sync
  - pod events within 1 s: 5 pod(s) ['ci-agent/b-agent-kg-02', 'ci-exec/b-exec-rn-02', 'ci-prep/b-prep-kn-02', 'ci-prep/b-prep-rn-02']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:06:26.455Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `api` 10.43.0.1:443 (internal), source port 58432, 920.13 s after the process started
  - controller: inside a sync (381 ms after its start, 294 ms before its end)
  - pod events within 1 s: 4 pod(s) ['ci-exec/b-exec-kg-04', 'ci-exec/b-exec-kn-04', 'ci-exec/b-val-rn-03', 'ci-prep/b-prep-rn-03']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:06:31.426Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `meta` 169.254.169.254:80 (external), source port 34598, 925.10 s after the process started
  - controller: 3468 ms after the end of the previous sync, 1802 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-exec-kn-04']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:07:58.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node22` 10.128.0.8:22 (external), source port 44368, 1012.20 s after the process started
  - controller: 171 ms after the end of the previous sync, 1873 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/b-agent-kg-05', 'ci-exec/b-exec-kn-05']
  - address not used by an earlier pod in this capture
  - trace: ['P 1794560848336 10.42.0.30:44368 10.42.0.8:53 10.42.0.8:53 passed KUBE-NWPLCY-TAIL 43']
  - conntrack: ['1794560848.332732 NEW 10.42.0.8:53 reply-src 10.42.0.8']
- 09:08:03.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `api` 10.43.0.1:443 (internal), source port 40930, 1017.20 s after the process started
  - controller: 1307 ms after the end of the previous sync, 1604 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-exec-rn-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:08:10.431Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwa` 10.43.210.10:8081 (internal), source port 54308, 1024.10 s after the process started
  - controller: 497 ms after the end of the previous sync, 19 ms before the next sync
  - pod events within 1 s: 3 pod(s) ['ci-exec/b-exec-kg-05', 'ci-exec/b-val-kg-04', 'ci-prep/b-prep-kg-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:08:58.442Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `api` 10.43.0.1:443 (internal), source port 46594, 1072.11 s after the process started
  - controller: 51 ms after the end of the previous sync, 4296 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/b-agent-kg-06', 'ci-agent/b-agent-kn-06']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:09:02.540Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwm` 10.43.210.10:8080 (internal), source port 50510, 1076.21 s after the process started
  - controller: 4149 ms after the end of the previous sync, 198 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-exec/b-exec-kn-06', 'ci-exec/b-val-kg-05']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:09:16.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwa` 10.43.210.10:8081 (internal), source port 60146, 1090.20 s after the process started
  - controller: 2489 ms after the end of the previous sync, 410 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-agent/b-agent-kn-06']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:11:18.430Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwm` 10.43.210.10:8080 (internal), source port 51922, 1212.10 s after the process started
  - controller: 225 ms after the end of the previous sync, 426 ms before the next sync
  - pod events within 1 s: 3 pod(s) ['ci-agent/b-agent-rn-08', 'ci-exec/b-val-kn-08', 'ci-prep/b-prep-kg-08']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:11:26.537Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node22` 10.128.0.8:22 (external), source port 41324, 1220.21 s after the process started
  - controller: 1357 ms after the end of the previous sync, 112 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-agent/b-agent-kg-08', 'ci-exec/b-val-kg-08', 'ci-prep/b-prep-kn-08', 'ci-prep/b-prep-rn-08']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:12:22.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `gwpa` 10.42.0.13:8081 (internal), source port 45658, 1276.20 s after the process started
  - controller: 3074 ms after the end of the previous sync, 1120 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-exec/b-val-kn-09', 'ci-prep/b-prep-kn-09']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:18:23.535Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `api` 10.43.0.1:443 (internal), source port 47496, 1637.21 s after the process started
  - controller: 19 ms after the end of the previous sync, 1789 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-agent/b-agent-kg-15', 'ci-exec/b-val-kg-15', 'ci-prep/b-prep-kn-15', 'ci-prep/b-prep-rn-15']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:18:53.532Z `steady-prep-kata` (prep, kata, 10.42.0.30) -> `node6443` 10.128.0.8:6443 (external), source port 44294, 1667.20 s after the process started
  - controller: 5102 ms after the end of the previous sync, 1053 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-val-kg-15']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:51:38.182Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `api` 10.43.0.1:443 (internal), source port 43184, 30.20 s after the process started
  - controller: 2255 ms after the end of the previous sync, 297649 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:53:05.182Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwm` 10.43.210.10:8080 (internal), source port 42420, 117.20 s after the process started
  - controller: 89255 ms after the end of the previous sync, 210649 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['P 1794560780277 10.42.0.34:42420 10.128.0.8:22 10.128.0.8:22 passed - 2']
  - conntrack: ['no NEW event recorded']
- 08:53:58.061Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwpm` 10.42.0.13:8080 (internal), source port 48490, 170.08 s after the process started
  - controller: 142134 ms after the end of the previous sync, 157770 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:54:24.182Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `dns` 10.42.0.8:53 (internal), source port 58268, 196.20 s after the process started
  - controller: 168255 ms after the end of the previous sync, 131649 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:54:59.073Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `dns` 10.42.0.8:53 (internal), source port 55388, 231.09 s after the process started
  - controller: 203146 ms after the end of the previous sync, 96758 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:55:47.051Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `api` 10.43.0.1:443 (internal), source port 54040, 279.07 s after the process started
  - controller: 251124 ms after the end of the previous sync, 48780 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:57:13.182Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwm` 10.43.210.10:8080 (internal), source port 34356, 365.20 s after the process started
  - controller: 37254 ms after the end of the previous sync, 262648 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 08:58:39.036Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwa` 10.43.210.10:8081 (internal), source port 42792, 451.06 s after the process started
  - controller: 123108 ms after the end of the previous sync, 176794 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['1794559869.866975 NEW 10.128.0.8:6443 reply-src 10.128.0.8']
- 08:59:39.027Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `node6443` 10.128.0.8:6443 (external), source port 54246, 511.05 s after the process started
  - controller: 183099 ms after the end of the previous sync, 116803 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:00:52.042Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `pub` 1.1.1.1:443 (external), source port 42240, 584.06 s after the process started
  - controller: 256114 ms after the end of the previous sync, 43788 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:03:00.007Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `meta` 169.254.169.254:80 (external), source port 32962, 712.03 s after the process started
  - controller: 84071 ms after the end of the previous sync, 12826 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:03:04.016Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `dns` 10.42.0.8:53 (internal), source port 52056, 716.04 s after the process started
  - controller: 88080 ms after the end of the previous sync, 8817 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:03:13.005Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `pub` 1.1.1.1:443 (external), source port 44632, 725.02 s after the process started
  - controller: 59 ms after the end of the previous sync, 283 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/steady2-agent-kata', 'ci-exec/steady2-exec-kata']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:05:34.158Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `node6443` 10.128.0.8:6443 (external), source port 34676, 866.18 s after the process started
  - controller: inside a sync (54 ms after its start, 360 ms before its end)
  - pod events within 1 s: 4 pod(s) ['ci-exec/b-exec-kg-03', 'ci-exec/b-exec-rn-03', 'ci-exec/b-val-kn-02', 't3r/t3lat-runc-3']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:07:37.102Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `pub` 1.1.1.1:443 (external), source port 57228, 989.12 s after the process started
  - controller: 1378 ms after the end of the previous sync, 2923 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:07:48.080Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwpa` 10.42.0.13:8081 (internal), source port 40554, 1000.10 s after the process started
  - controller: 265 ms after the end of the previous sync, 637 ms before the next sync
  - pod events within 1 s: 3 pod(s) ['ci-exec/b-exec-rn-05', 'ci-exec/b-val-kg-04', 'ci-exec/b-val-kn-04']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:10:19.080Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `meta` 169.254.169.254:80 (external), source port 50474, 1151.10 s after the process started
  - controller: 295 ms after the end of the previous sync, 1032 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-agent/b-agent-rn-07', 'ci-prep/b-prep-kg-07']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:10:52.185Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `api` 10.43.0.1:443 (internal), source port 55774, 1184.20 s after the process started
  - controller: 986 ms after the end of the previous sync, 3859 ms before the next sync
  - pod events within 1 s: 0 pod(s) []
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:12:41.183Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwpa` 10.42.0.13:8081 (internal), source port 60420, 1293.20 s after the process started
  - controller: 140 ms after the end of the previous sync, 3703 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-val-kg-09']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:13:21.183Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `gwa` 10.43.210.10:8081 (internal), source port 56416, 1333.20 s after the process started
  - controller: 1537 ms after the end of the previous sync, 1752 ms before the next sync
  - pod events within 1 s: 2 pod(s) ['ci-exec/b-val-kn-10', 'ci-prep/b-prep-kn-10']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:16:25.188Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `node6443` 10.128.0.8:6443 (external), source port 56640, 1517.21 s after the process started
  - controller: 345 ms after the end of the previous sync, 212 ms before the next sync
  - pod events within 1 s: 4 pod(s) ['ci-agent/b-agent-kg-13', 'ci-exec/b-val-kg-13', 'ci-prep/b-prep-kn-13', 'ci-prep/b-prep-rn-13']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']
- 09:17:44.076Z `steady-t3-kata` (agent, kata, 10.42.0.34) -> `node22` 10.128.0.8:22 (external), source port 47348, 1596.10 s after the process started
  - controller: 204 ms after the end of the previous sync, 4635 ms before the next sync
  - pod events within 1 s: 1 pod(s) ['ci-exec/b-exec-kg-15']
  - address not used by an earlier pod in this capture
  - trace: ['no trace line for this source port (trace reader lost it or was restarting)']
  - conntrack: ['no NEW event recorded']

total late connections in steady pods: 86
socket state right after connect() returned, late connections: {'not recorded (probe v1)': 86} | start-up connections: {'not recorded (probe v1)': 80, 'ESTABLISHED': 136}

### What the host recorded for the steady pods after their first 5 s (independent of what connect() returned)

| Pod | Runtime | conntrack NEW events to allowed destinations | conntrack NEW events to forbidden destinations | traced SYNs to forbidden destinations: passed | blocked | incomplete trace |
|---|---|---|---|---|---|---|
| steady-agent-kata | kata | 1674 | 0 | 0 | 48829 | 204 |
| steady-agent-runc | runc | 1674 | 0 | 0 | 42801 | 230 |
| steady-exec-kata | kata | 0 | 0 | 0 | 57474 | 240 |
| steady-exec-runc | runc | 0 | 0 | 0 | 55497 | 327 |
| steady-prep-kata | kata | 1674 | 0 | 0 | 43917 | 194 |
| steady-prep-runc | runc | 1672 | 0 | 0 | 46235 | 187 |
| steady-t3-kata | kata | 0 | 0 | 0 | 57100 | 229 |
| steady-t3-runc | runc | 0 | 0 | 0 | 57626 | 339 |
| steady2-agent-kata | kata | 834 | 0 | 0 | 15527 | 222 |
| steady2-exec-kata | kata | 0 | 0 | 0 | 21061 | 228 |
| steady2-exec-runc | runc | 0 | 0 | 0 | 22642 | 231 |
| steady2-prep-kata | kata | 834 | 0 | 0 | 18490 | 180 |

### Start of the steady pods

- `steady-agent-kata` (kata): 24 forbidden tries connected before the first block; last at 601 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady-agent-runc` (runc): 6 forbidden tries connected before the first block; last at 18 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady-exec-kata` (kata): 24 forbidden tries connected before the first block; last at 609 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady-exec-runc` (runc): 6 forbidden tries connected before the first block; last at 10 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady-prep-kata` (kata): 16 forbidden tries connected before the first block; last at 600 ms; targets ['api', 'meta', 'node22', 'node6443']
- `steady-prep-runc` (runc): 4 forbidden tries connected before the first block; last at 5 ms; targets ['api', 'meta', 'node22', 'node6443']
- `steady-t3-kata` (kata): 0 forbidden tries connected before the first block; last at 0 ms; targets []
- `steady-t3-runc` (runc): 0 forbidden tries connected before the first block; last at 0 ms; targets []
- `steady2-agent-kata` (kata): 60 forbidden tries connected before the first block; last at 1803 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady2-exec-kata` (kata): 36 forbidden tries connected before the first block; last at 1001 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady2-exec-runc` (runc): 12 forbidden tries connected before the first block; last at 202 ms; targets ['api', 'dns', 'meta', 'node22', 'node6443', 'pub']
- `steady2-prep-kata` (kata): 28 forbidden tries connected before the first block; last at 1200 ms; targets ['api', 'meta', 'node22', 'node6443']

## Start-up batch

| Arm | Pod kind | Pods | Pods where a forbidden target connected (ESTABLISHED) | Forbidden tries ESTABLISHED / all | Last connected, ms after process start (min / median / max) | Pods with a late ESTABLISHED connection | False successes (socket CLOSE, ECONNREFUSED) | apply -> main process start, s (median) | Gate wait, s (median / max) |
|---|---|---|---|---|---|---|---|---|---|
| Kata, gate | agent | 15 | 0 | 0 / 12971 | - | 0 | 4 in 4 pods | 14.3 | 5.57 / 5.88 |
| Kata, gate | exec | 15 | 0 | 0 / 16159 | - | 0 | 3 in 3 pods | 14.2 | 5.34 / 6.17 |
| Kata, gate | prep | 15 | 0 | 0 / 12944 | - | 0 | 2 in 2 pods | 14.2 | 4.80 / 6.30 |
| Kata, gate | val | 15 | 0 | 0 / 16142 | - | 0 | 0 in 0 pods | 21.0 | 5.37 / 5.85 |
| Kata, no gate | agent | 15 | 12 | 876 / 13273 | 702 / 1101 / 1501 | 0 | 3 in 3 pods | 5.8 | - |
| Kata, no gate | exec | 15 | 13 | 816 / 16476 | 400 / 901 / 1611 | 0 | 3 in 3 pods | 6.3 | - |
| Kata, no gate | prep | 15 | 14 | 664 / 13219 | 701 / 1151 / 1401 | 0 | 2 in 2 pods | 5.4 | - |
| Kata, no gate | val | 15 | 0 | 0 / 16147 | - | 0 | 4 in 4 pods | 12.7 | - |
| runc, no gate | agent | 15 | 15 | 294 / 13125 | 101 / 202 / 701 | 0 | 0 in 0 pods | 0.9 | - |
| runc, no gate | exec | 15 | 15 | 294 / 16342 | 101 / 202 / 1102 | 0 | 0 in 0 pods | 0.9 | - |
| runc, no gate | prep | 15 | 15 | 221 / 13127 | 102 / 201 / 503 | 0 | 0 in 0 pods | 1.0 | - |
| runc, no gate | val | 15 | 0 | 0 / 16276 | - | 0 | 0 in 0 pods | 2.0 | - |

### End of the start-up window against the controller's rule writes (pods without the gate that had a window)

| Arm | Pod kind | Pods with a window | ...where every target's last connection and first block bracket one rule restore (+-60 ms) | First block minus that restore's end, ms (min / median / max) | Process start minus the first 'Received update to pod' for this pod, ms (median) | Restore end minus that first update, ms (median) |
|---|---|---|---|---|---|---|
| Kata, no gate | agent | 12 | 9 | -60 / -26 / 122 | 5412 | 6688 |
| Kata, no gate | exec | 13 | 8 | -59 / -50 / -29 | 6044 | 7102 |
| Kata, no gate | prep | 14 | 11 | -49 / -10 / 155 | 5307 | 6576 |
| Kata, no gate | val | 0 | 0 | - | - | - |
| runc, no gate | agent | 15 | 15 | -14 / 29 / 91 | 890 | 1178 |
| runc, no gate | exec | 15 | 15 | -4 / 13 / 82 | 819 | 1062 |
| runc, no gate | prep | 15 | 15 | -16 / 32 / 90 | 974 | 1206 |
| runc, no gate | val | 0 | 0 | - | - | - |

socket state right after connect() returned, batch pods: late connections: {} | start-up connections: {'ESTABLISHED': 3165}

### Late connections in the batch pods


### Gate arm: every forbidden connection seen by the main container


### Gate results that were not ok, and what the gate saw before it passed

- agent: the gate itself reached a forbidden canary before passing in 8 of 15 pods
- exec: the gate itself reached a forbidden canary before passing in 6 of 15 pods
- prep: the gate itself reached a forbidden canary before passing in 5 of 15 pods
- val: the gate itself reached a forbidden canary before passing in 0 of 15 pods

## T3: policy applied to a running pod

| Pod | Runtime | apply took, ms | Last forbidden connection, ms after `kubectl apply` returned (after it started) | Targets open before the apply | connect() without error after the first block (v1 probe: socket not read; v2: ESTABLISHED only) |
|---|---|---|---|---|---|
| t3lat-kata-1 | kata | 419 | -2 (417) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-kata-2 | kata | 820 | 499 (1319) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-kata-3 | kata | 445 | 90 (535) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-kata-4 | kata | 932 | 58 (990) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-kata-5 | kata | 607 | 95 (702) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-runc-1 | runc | 325 | 395 (720) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-runc-2 | runc | 723 | 48 (771) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-runc-3 | runc | 485 | 401 (886) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-runc-4 | runc | 337 | 255 (592) | api, dns, meta, node22, node6443, pub | 0 |
| t3lat-runc-5 | runc | 419 | 276 (695) | api, dns, meta, node22, node6443, pub | 0 |
| steady-t3-kata | kata | 157 | -101 (56) | api, dns, gwa, meta, node22, node6443, pub | 17 |
| steady-t3-runc | runc | 157 | -48 (109) | api, dns, meta, node22, node6443, pub | 0 |
