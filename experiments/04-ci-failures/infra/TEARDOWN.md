# Teardown plan

> Translated from the Portuguese original. The project id is replaced by `<your-project>`; the scripts read it from
> `AIP_PROJECT` and never use the gcloud default.

Scope: only the VM `aip-ci-01` and its disk, in the explicit project, with the labels `owner=aip` **and**
`experiment=aip-v05-ci`. No other resource of the project is listed or touched. The Secret with the Anthropic key
exists only inside the cluster on that VM and disappears with the disk (the disk is deleted with it:
`--delete-disks=all`).

Before (on your machine; nothing runs on the VM after this):
1. Copy what is still only on the VM: `results/`, `capture/casts/`, `cases/*.jsonl`, `cases/*.csv`, `smoke/` (for
   example with `gcloud compute ssh aip-ci-01 … --command 'cd ~/lab && tar czf - …'`).
2. Check that `cases/cases.csv` has the sha256 `d0abec78…a5b8` (`cases/cases.csv.sha256`) and that the blind packets
   and the key are saved.

Teardown:
```
AIP_PROJECT=<your-project> infra/destroy.sh     # selects name~^aip- AND labels.owner=aip AND labels.experiment=aip-v05-ci;
                                                # refuses if any instance other than aip-ci-01 shows up; deletes it with its disks
AIP_PROJECT=<your-project> infra/list.sh        # must show "instances: none" and "disks: none"
```
Independent check (read-only, filtered by the channel's name prefix):
```
for k in instances disks snapshots images addresses firewall-rules; do
  gcloud compute $k list --project <your-project> --filter="name~^aip-" --format="value(name)"; done
```
Afterwards: record the VM's cost (start 2026-11-11T16:21Z, end = time of deletion, about US$ 0.42/h at list price) and
the time in `results/timeline.txt`.
