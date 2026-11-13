#!/usr/bin/env bash
# 2026-11-13, runs ON the VM. Starts the host-side recorders for one phase: pod and NetworkPolicy events, rule-set
# snapshots, the packet trace of pod SYNs, conntrack events for pod sources. usage: start-capture.sh <out-dir>; stop with stop-capture.sh
out="$1"; mkdir -p "$out"; cd "$(dirname "$0")"
sudo iptables -t raw -C PREROUTING -s 10.42.0.0/16 -p tcp -m tcp --tcp-flags SYN,ACK,FIN,RST SYN -m comment --comment "aip-trace pod SYN" -j TRACE 2>/dev/null ||
  sudo iptables -t raw -I PREROUTING 1 -s 10.42.0.0/16 -p tcp -m tcp --tcp-flags SYN,ACK,FIN,RST SYN -m comment --comment "aip-trace pod SYN" -j TRACE
date -u +%FT%T.%3NZ > "$out/capture-start.txt"
nohup python3 podwatch.py pods "$out/pod-events.jsonl" > /dev/null 2>&1 &
nohup python3 podwatch.py networkpolicies "$out/netpol-events.jsonl" > /dev/null 2>&1 &
sudo nohup python3 rulewatch.py "$out/rules" 0.5 > /dev/null 2>&1 &
mkdir -p "$out/trace"   # the raw trace stays on the VM (large); the filter reads it as it grows
sudo nohup ./trace-loop.sh "$out/trace" xt > /dev/null 2>&1 &
sudo nohup ./trace-loop.sh "$out/trace" nft > /dev/null 2>&1 &
sudo nohup bash -c "tail -n +1 -F '$out/trace/raw-trace.log' 2>/dev/null | python3 tracefilter.py '$out/trace'" > "$out/trace/filter.err" 2>&1 &
sudo nohup bash -c "conntrack -E -o timestamp -p tcp 2>/dev/null | grep --line-buffered -e 'src=10\.42\.0\.[0-9]* dst=' > '$out/conntrack-events.log'" > /dev/null 2>&1 &
sleep 1; pgrep -fa "podwatch|rulewatch|tracefilter|xtables-monitor|conntrack -E" | cut -c1-90
