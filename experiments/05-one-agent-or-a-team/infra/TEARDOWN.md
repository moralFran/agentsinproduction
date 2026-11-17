# Teardown plan (NOT executed; only with Francisco's authorization)

> Translated from the Portuguese original, which is kept in the author's private production repository. The GCP
> project id is replaced by `<your-project>`. Other edits for the public copy, marked in square brackets: the project's
> name, a folder of the private production repository and the cost ledger are described instead of named. Nothing else
> was changed, shortened or reworded in substance.
>
> [Note for the public copy: this plan was carried over from experiment 04 when this folder was created and was not
> updated afterwards. The `cd`, the `cases.csv` check, the start time and the hourly cost below are experiment 04's,
> and "NOT executed" was true when it was written. This experiment's VM was deleted on 16/11/2026 at 21:55:41 UTC with
> Francisco's authorization (explicit project, labels checked, disk deleted with it); see the last section
> of [`criteria.md`](../criteria.md). Its machine cost was US$ 16.87 at list price.]

Scope: only the VM `aip-ci-01` and its disk, in the explicit project, with the labels `owner=aip` **and**
`experiment=aip-v06-team`. No other resource of [the GCP project; its name is redacted for the public copy] is listed
or touched. The Secret with the Anthropic key exists only inside the cluster on that VM and disappears with the disk
(the disk is deleted with it: `--delete-disks=all`).

Before (on the Mac; nothing runs on the VM after this):
1. Copy what is still only on the VM: `results/`, `capture/casts/`, `cases/*.jsonl`, `cases/*.csv`, `smoke/` (already
   copied up to v2; repeat the final copy with a call `gcloud compute ssh aip-ci-01 … --command 'cd ~/lab && tar czf - …'`).
2. Check in git that `cases/cases.csv` has the sha256 `d0abec78…a5b8` and that the blind packets and the key are
   committed.

Teardown, recording the capture of the clean-up as in V4:
```
cd [the folder of experiment 04 (CI failures) in the private production repository]
AIP_PROJECT=<your-project> infra/destroy.sh     # selects name~^aip- AND labels.owner=aip AND labels.experiment=aip-v06-team;
                                                # refuses if any instance other than aip-ci-01 shows up; deletes it with its disks
AIP_PROJECT=<your-project> infra/list.sh        # must show "instances: none" and "disks: none"
```
Independent check (read-only, filtered by the channel's name prefix):
```
for k in instances disks snapshots images addresses firewall-rules; do
  gcloud compute $k list --project <your-project> --filter="name~^aip-" --format="value(name)"; done
```
Afterwards: close the VM's cost in [the cost ledger in the private production repository] (start 2026-11-11T16:21Z,
end = time of the destruction, ~US$ 0.42/h at list price) and record the time in `results/timeline.txt`.
