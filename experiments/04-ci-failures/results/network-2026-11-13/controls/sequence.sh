#!/usr/bin/env bash
# 2026-11-13, runs ON the VM under nohup: everything after the main block, in order, so that a lost SSH session changes
# nothing. Each step writes into its own folder; progress in ~/net/post/sequence.log.
export KUBECONFIG=~/.kube/config; cd ~/net; mkdir -p post race t7 t5; exec >> post/sequence.log 2>&1
say() { echo "$(date -u +%FT%TZ) $*"; }; C=~/net/controls; CID=gobwas-ws-a567dfd6; PATCH=~/lab/results/patches/v1/v1-e88f0806-r1.diff
say "1. end of the main block: stop the batch driver, the recorders, delete what is left"
date -u +%FT%T.%3NZ > main/churn-end.txt; date +%s%3N >> main/churn-end.txt
pkill -f "run-watch-pods.py.*plan-batch.json"; sudo pkill tcpdump
$C/stop-capture.sh ~/net/main/cap "08:50:00"
for ns in ci-exec ci-agent ci-prep t3 t3k t3r; do kubectl -n $ns delete pods --all --wait=false; done; kubectl -n ci-exec get configmap -o name | grep -- -patch | xargs -r kubectl -n ci-exec delete
sudo chmod a+r main/cap/cni0-syn-rst-icmp.pcap
say "2. host-side evidence for the main block (background)"
( nice python3 $C/late-lookup.py main/cap main/t3-steady-apply.jsonl main/late-events.jsonl main/steady main/steady2 main/batch main/t3lat > main/late-lookup-summary.txt 2>&1
  nice python3 $C/nft-verdicts.py main/cap/trace/raw-nft-trace.log main/nft-verdicts main/t3-steady-apply.jsonl main/steady main/steady2 main/batch main/t3lat > main/nft-verdicts-summary.txt 2>&1; say "2. done" ) &
sleep 20
say "3. connect() race pods (probe version 3, raw system calls) with their own capture"
cat > race/plan.json <<P
{"concurrency": 6, "stagger": 0.5, "pods": [
 {"name": "race-exec-kata-1", "kind": "exec-repro", "runtime": "kata", "gate": false, "seconds": 300, "interval": 0.2, "raw": true},
 {"name": "race-exec-kata-2", "kind": "exec-repro", "runtime": "kata", "gate": false, "seconds": 300, "interval": 0.2, "raw": true},
 {"name": "race-agent-kata", "kind": "agent", "runtime": "kata", "gate": false, "seconds": 300, "interval": 0.2, "raw": true},
 {"name": "race-exec-runc-1", "kind": "exec-repro", "runtime": "runc", "gate": false, "seconds": 300, "interval": 0.2, "raw": true},
 {"name": "race-exec-runc-2", "kind": "exec-repro", "runtime": "runc", "gate": false, "seconds": 300, "interval": 0.2, "raw": true}]}
P
$C/start-capture.sh ~/net/race/cap > /dev/null
sudo nohup tcpdump -i cni0 -n -s 96 -w /home/$USER/net/race/cap/cni0-syn-rst-icmp.pcap "(icmp or (tcp[tcpflags] & (tcp-syn|tcp-rst) != 0)) and net 10.42.0.0/24" > /dev/null 2>&1 &
python3 $C/run-watch-pods.py ~/run $CID ~/net/race/pods $PATCH race/plan.json > race/driver.log 2>&1 &
RACE=$!
say "4. T7: redeploy with the four changed files, then checks A B D (C in parallel)"
$C/t7-redeploy.sh ~/run ~/net/t7
( $C/t7-checks.sh ~/run ~/net/t7/c $CID C ) &
TC=$!
$C/t7-checks.sh ~/run ~/net/t7 $CID A B D
say "4. A B D done"; wait $TC; say "4. C done"; wait $RACE; say "3. race pods done"
cp ~/net/t7/c/C-* ~/net/t7/ 2>/dev/null
say "5. stop the race capture, look up its events"
sudo pkill tcpdump; $C/stop-capture.sh ~/net/race/cap "09:15:00"; sudo chmod a+r race/cap/cni0-syn-rst-icmp.pcap
python3 $C/late-lookup.py race/cap - race/late-events.jsonl race/pods > race/late-lookup-summary.txt 2>&1
python3 $C/nft-verdicts.py race/cap/trace/raw-nft-trace.log race/nft-verdicts - race/pods > race/nft-verdicts-summary.txt 2>&1
say "6. T5: guest seccomp on, then one pod of each kind with and without the gate (one at a time), then a real reproduction"
$C/t5-seccomp.sh ~/net/t5
python3 - > t5/plan.json <<'PY'
import json
pods = [{"name": f"t5-{s}-{'g' if g else 'n'}", "kind": k, "runtime": "kata", "gate": g, "seconds": 8, "interval": 0.1, "timeout": 0.15}
        for g in (False, True) for k, s in (("exec-repro", "exec"), ("agent", "agent"), ("prep", "prep"), ("exec-validate", "val"))]
print(json.dumps({"concurrency": 1, "pods": pods}))
PY
python3 $C/run-watch-pods.py ~/run $CID ~/net/t5/pods $PATCH t5/plan.json > t5/driver.log 2>&1
say "6b. reproduction of $CID with guest seccomp on and the gate in every pod"
( cd ~/run && REPRO_OUT=~/net/t5/repro-seccomp.jsonl cases/repro.sh $CID 3; echo "repro.sh rc=$?" ) > t5/repro.log 2>&1
for p in rb rf rh rc; do cp /srv/ci/logs/$p-$CID.log t5/ 2>/dev/null; done
say "SEQUENCE_DONE"
