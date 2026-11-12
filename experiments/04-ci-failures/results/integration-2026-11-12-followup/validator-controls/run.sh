#!/usr/bin/env bash
cd ~/run2
for c in "gobwas-ws-a567dfd6 control-test-file" "gobwas-ws-a567dfd6 control-ci-file" "openbyteinc-quantdinger-733f7bc7 control-probe"; do set -- $c
  python3 cases/validate.py $1 ~/int2/validator-controls/$2.diff "vc-$2" > ~/int2/validator-controls/$2.out 2>&1; echo "$2 rc=$?"; done
echo VC_DONE
