#!/usr/bin/env bash
# Sourced by the diagnostics. Every run has an id, RUN, and writes results/<name>-$RUN.<ext>; an existing file is
# never overwritten (the files without a suffix are the collection of 2026-11-11).
#   out <name> <ext>  -> prints the path, or fails if it exists
: "${RUN:?set RUN to an id for this run, for example RUN=r4: result files get it as a suffix and nothing is overwritten}"
out() {
  local f="results/$1-$RUN.$2"
  [ ! -e "$f" ] || { echo "$f already exists; choose another RUN id" >&2; return 1; }
  mkdir -p results; echo "$f"
}
