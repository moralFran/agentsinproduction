#!/usr/bin/env bash
cd ~/lab
step() { n="$1"; shift; echo "$(date -u +%FT%TZ) START $n" >> ~/net/setup/timeline.txt; "$@" > ~/net/setup/$n.log 2>&1; echo "$(date -u +%FT%TZ) END $n rc=$?" >> ~/net/setup/timeline.txt; }
step 01-install-docker infra/install-docker.sh
step 02-install-k3s-kata infra/install-k3s-kata.sh
step 03-build-images infra/build-images.sh
step 04-setup-lab bash -c "printf dummy-not-a-key | infra/setup-lab.sh"
step 05-new-run infra/new-run.sh ~/run --with-candidates
echo "$(date -u +%FT%TZ) BUILD_DONE" >> ~/net/setup/timeline.txt
