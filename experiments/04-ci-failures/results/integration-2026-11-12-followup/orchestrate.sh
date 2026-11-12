#!/usr/bin/env bash
# waits for the reproduction of the ten cases other than cosign, then starts the re-validation of their patches (2 lanes);
# when every pipeline worker has ended: the freeze gate check, then the cosign patches (1 lane).
cd ~/int2; mkdir -p revalidation freeze
others="gobwas-ws-a567dfd6 tdewolff-minify-fa882446 mark3labs-mcp-go-1969a6b9 alicebob-miniredis-ce093519 ludwig-ai-ludwig-6a122a8e pyinfra-dev-pyinfra-e7e42b68 rmax-scrapy-redis-8d8672f2 nkanaev-yarr-957e81dd boyter-scc-4288f7c8 openbyteinc-quantdinger-733f7bc7"
ready() { for c in $others; do grep -q "\"id\": \"$c\"" ~/run2/cases/repro.jsonl || return 1; done; }
until ready; do sleep 10; done; echo "$(date -u +%T) ten cases reproduced; starting lane A"
python3 controls/revalidate.py ~/lab ~/run2 ~/int2/revalidation 2 "$(echo $others | tr " " ",")" > revalidation/driver-A.log 2>&1 &
until [ "$(pgrep -fc "cases/pipeline.sh")" = 0 ]; do sleep 10; done; echo "$(date -u +%T) pipeline ended; freeze gate check"
controls/freeze-gate-check.sh ~/run2 ~/int2/freeze; echo "$(date -u +%T) starting lane B (cosign)"
python3 controls/revalidate.py ~/lab ~/run2 ~/int2/revalidation 1 sigstore-cosign-1ab7015b > revalidation/driver-B.log 2>&1
wait; echo "$(date -u +%T) ORCHESTRATION_DONE"
