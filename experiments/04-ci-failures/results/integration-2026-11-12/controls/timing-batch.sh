#!/usr/bin/env bash
# Integration (2026-11-12), runs ON the VM. Repeats the policy-timing probe (nettime.py, 12 s each) N times for each pod kind.
# usage: timing-batch.sh <label> <n> [kinds]     output: ~/int/network/timing/probe-<kind>-<label><i>.log
cd ~/int; label="$1"; n="$2"; kinds="${3:-exec-repro,agent,prep,exec-validate-suite}"
for i in $(seq 1 "$n"); do
  echo "$(date -u +%T) load $(cut -d' ' -f1 /proc/loadavg) $label$i"
  PROBE_FILE=nettime.py NETTIME_SECONDS=12 NAME_SUFFIX="-$label$i" python3 controls/run-probe-pods.py ~/run gobwas-ws-a567dfd6 ~/int/network/timing ~/lab/results/patches/v1/v1-e88f0806-r1.diff "$kinds"
done
echo "$(date -u +%T) DONE"
