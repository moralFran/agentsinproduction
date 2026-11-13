#!/usr/bin/env bash
# 2026-11-13, runs ON the VM. Stops the recorders and saves the k3s journal since <since> (journalctl time) to <out-dir>.
out="$1"; since="$2"
sudo pkill -f podwatch.py; sudo pkill -f rulewatch.py; sudo pkill -f trace-loop.sh; sudo pkill -f "xtables-monitor --trace"; sudo pkill -f "nft monitor trace"; sudo pkill -f "conntrack -E"; sleep 2.5; sudo pkill -f "tail -n +1 -F"; sleep 0.5; sudo pkill -f tracefilter.py
sudo journalctl -u k3s --since "$since" -o short-iso-precise --no-pager | grep -E "npc_iptables|policy.go|pod.go:|namespace.go|netpol|network policy|ipset" | gzip > "$out/k3s-journal-netpol.log.gz"
sudo journalctl -u k3s --since "$since" -o short-iso-precise --no-pager | gzip > "$out/k3s-journal-full.log.gz"
date -u +%FT%T.%3NZ > "$out/capture-stop.txt"; sudo chown -R "$USER" "$out"; du -sh "$out"
