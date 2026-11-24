#!/usr/bin/env bash
# Runs ON aip-ctx-01. Prints every version and digest of the lab (VM, cluster, box image, tools inside the image,
# dependency sets). The output is stored as infra/versions.txt in the experiment folder.
set -uo pipefail
export KUBECONFIG=~/.kube/config
IMAGE="${BOX_IMAGE:-aip-team-box:1}"
echo "# lab versions, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "vm: $(hostname -s), $(nproc) vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, $(lsb_release -ds), kernel $(uname -r)"
echo "docker.io: $(dpkg-query -W -f='${Version}' docker.io 2>/dev/null)"
echo "k3s: $(k3s --version | head -1)"
echo "containerd: $(sudo k3s ctr version 2>/dev/null | awk '/Version:/{print $2}' | head -1)"
echo "helm: $(helm version --short 2>/dev/null)"
echo "kata-deploy chart: $(helm -n kube-system list 2>/dev/null | awk '/kata-deploy/{print $9, $10}')"
echo "kata runtime: $(/opt/kata/bin/kata-runtime --version 2>/dev/null | head -1)"
echo "kata drop-ins (qemu): $(sudo ls /opt/kata/share/defaults/kata-containers/runtimes/qemu/config.d 2>/dev/null | tr '\n' ' ')"
echo "kube-router (network policy): $(kubectl version 2>/dev/null | tr '\n' ' ')"
echo
echo "## box image $IMAGE"
echo "base: $(grep -m1 '^base:' ~/logs/build-image.log | sed 's/^base: //')"
echo "docker image id: $(sudo docker inspect --format '{{.Id}}' "$IMAGE")"
echo "containerd: $(sudo k3s ctr images ls | grep "${IMAGE%%:*}" | awk '{print $1, $3, $4 $5}')"
echo "Dockerfile.box sha256: $(sha256sum ~/lab/infra/Dockerfile.box | cut -d' ' -f1)"
sudo docker run --rm --network none "$IMAGE" sh -c '
  . /etc/os-release; echo "os: $PRETTY_NAME"; echo "user: $(id)"; echo "HOME=$HOME PUB_CACHE=$PUB_CACHE FIREBASE_EMULATORS_PATH=$FIREBASE_EMULATORS_PATH"
  flutter --version 2>&1 | head -4; echo "dart: $(dart --version 2>&1)"
  echo "node: $(node --version)  npm: $(npm --version)"; java -version 2>&1 | head -3
  echo "firebase-tools: $(firebase --version)"; echo "emulator files:"; cd "$FIREBASE_EMULATORS_PATH" && sha256sum *.jar *.zip 2>/dev/null
  /opt/agent-venv/bin/python -c "import anthropic, sys; print(\"python:\", sys.version.split()[0], \" anthropic:\", anthropic.__version__)"
  echo "git: $(git --version)"; echo "rsync: $(rsync --version | head -1)"
  echo "flutter analytics: $(flutter config 2>/dev/null | grep -i -m1 analytics)"; echo "dart analytics: $(cat ~/.dart-tool/dart-flutter-telemetry.config 2>/dev/null | grep -i reporting | head -1)"
  echo "flutter test artifacts: $(ls /opt/flutter/bin/cache/artifacts/engine/linux-x64/ | tr "\n" " ")"
  echo "flutter cache dirs: $(ls /opt/flutter/bin/cache/artifacts | tr "\n" " ")"' 2>&1
echo
echo "## dependency sets (/srv/ci/deps)"
for d in /srv/ci/deps/locks/*/; do echo "pub lock $(basename "$d"): sha256 $(sha256sum "$d/pubspec.lock" | cut -d' ' -f1), $(grep -c '^  [a-zA-Z0-9_]*:$' "$d/pubspec.lock") packages"; done
for d in /srv/ci/deps/node/*/; do echo "node set $(basename "$d"): $(cat "$d/DONE" 2>/dev/null), $(sudo ls "$d/node_modules" | wc -l) top-level entries"; done
echo "pub cache: $(sudo du -sh /srv/ci/deps/pub-cache | cut -f1)"
for t in /srv/ci/cases/T*/; do python3 - "$t" <<'PY'
import json, sys
m = json.load(open(sys.argv[1] + "meta.json")); print("task", m["id"], "snapshot", m["snapshot_commit"], "deps", m.get("dependency_sets"), "empty dirs:", m.get("empty_dirs_for_jest_roots", []))
PY
done
