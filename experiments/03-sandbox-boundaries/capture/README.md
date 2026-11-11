# Terminal captures of the video (A-v05)

Each capture is a short list of commands (`captures.json`, with the script scene it anchors). `play.py` runs on the
machine where the commands belong, "types" each one and then **runs it for real**; `record.sh` records the session
from the Mac with asciinema into `casts/` (text, 76x17, the size of the channel's 36 px terminal). Only the typing is
simulated. Recorded on 2026-11-11 against the lab of this experiment, after the second-review corrections.

- Live on the lab: the VM list, the host, versions and RuntimeClass, the NetworkPolicy, the gateway's mounts and its
  offline budget test (re-recorded after the third review), the agent's own pod (user, no token, no capabilities, deadline), the failing tests, the network
  probes without and with the policy, the two RBAC identities, the kernels, the sandbox processes, the validator
  (controls and one collected patch), the final configuration.
- Read from the collection's files (the numbers the narration uses): the attempts, the 10x tallies, the gateway and
  endpoint logs, start time and memory.

To record again (lab running): `capture/setup.sh a` on `aip-kata-01`, `AIP_PROJECT=… capture/record.sh <names of
phase_a>`, then `capture/setup.sh b` and the `phase_b` names, then `capture/setup.sh down`. `no_pods` captures need
no setup. The live probes use the phase name `once`, so the logs of the 10x collection stay countable.

To render MP4s with the channel's window (needs the media SSD): `pipeline/vhs/A-v05/render.sh`. VHS replays each cast
with its recorded timing; the first seconds of a cast are the SSH connection and are trimmed in the edit.

The lab was deleted on 2026-11-11T13:57Z (`c20-cleanup` is that deletion, recorded once; `c20b-nothing-left` is the
listing afterwards). Recording again means recreating the lab with `infra/` first.
