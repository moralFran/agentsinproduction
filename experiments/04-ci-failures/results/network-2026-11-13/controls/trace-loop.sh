#!/usr/bin/env bash
# 2026-11-13, runs ON the VM as root. xtables-monitor stopped by itself in the first minute of the main capture (08:51Z),
# so both trace readers run in a restart loop, each to its own raw file, with a line "### restart <epoch_ms> <tool> rc=<n>"
# whenever one exits. usage: trace-loop.sh <out-dir> xt|nft
out="$1"; tool="$2"; mkdir -p "$out"
while true; do
  if [ "$tool" = xt ]; then stdbuf -oL xtables-monitor --trace >> "$out/raw-trace.log" 2>> "$out/xt.err"; rc=$?; echo "### restart $(date +%s%3N) xtables-monitor rc=$rc" >> "$out/raw-trace.log"
  else stdbuf -oL nft monitor trace >> "$out/raw-nft-trace.log" 2>> "$out/nft.err"; rc=$?; echo "### restart $(date +%s%3N) nft-monitor rc=$rc" >> "$out/raw-nft-trace.log"; fi
  echo "$(date +%s%3N) $tool rc=$rc" >> "$out/restarts.log"; sleep 0.05
done
