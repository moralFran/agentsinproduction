#!/usr/bin/env bash
# Review follow-up (2026-11-13), runs ON the VM. NOT an empty machine: on the same VM, k3s is removed with its own
# uninstall script and what kata-deploy left under /opt/kata is deleted; then infra/install-k3s-kata.sh of the working
# tree runs as it is (first run of its `helm install ... -f <values>` line), the box image is imported again from the
# local Docker cache (infra/build-images.sh), infra/setup-lab.sh runs with the DUMMY key, and one gated pod of each
# kind is started. Docker, Helm, /srv/ci (one prepared case, admin key) and the run folder stay from before.
# usage: c-reinstall.sh <run-dir> <out-dir>
run="$1"; out="$2"; mkdir -p "$out"; cd "$run"; export KUBECONFIG=~/.kube/config
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$out/timeline.txt"; }
say "before: $(k3s --version | head -1); /opt/kata: $(sudo du -sh /opt/kata 2>/dev/null | cut -f1); drop-ins: $(sudo ls /opt/kata/share/defaults/kata-containers/runtimes/qemu/config.d 2>/dev/null | tr '\n' ' ')"
say "k3s-uninstall.sh"; sudo /usr/local/bin/k3s-uninstall.sh > "$out/01-k3s-uninstall.log" 2>&1; say "rc=$?"
sudo rm -rf /opt/kata; rm -f ~/.kube/config
say "after uninstall: k3s binary $(command -v k3s || echo absent); /opt/kata $(sudo ls /opt/kata 2>/dev/null | wc -l) entries; /var/lib/rancher $(sudo ls /var/lib/rancher 2>/dev/null | wc -l) entries; /etc/rancher $(sudo ls /etc/rancher 2>/dev/null | wc -l) entries"
sha256sum infra/install-k3s-kata.sh infra/setup-lab.sh | tee -a "$out/timeline.txt"
say "infra/install-k3s-kata.sh"; infra/install-k3s-kata.sh > "$out/02-install-k3s-kata.log" 2>&1; say "rc=$?"
K=/opt/kata/share/defaults/kata-containers/runtimes/qemu
{ echo "config.d: $(sudo ls -la $K/config.d | tail -n +2 | awk '{print $5, $9}' | tr '\n' ';')"; for f in $(sudo ls $K/config.d); do echo "--- $K/config.d/$f"; sudo cat "$K/config.d/$f"; done
  echo "--- base file"; sudo grep -n "disable_guest_seccomp" $K/configuration-qemu.toml; helm -n kube-system list --no-headers | awk '{print $1, "revision", $3, $8, $9}'
  helm -n kube-system get values kata-deploy; kubectl get runtimeclass kata-qemu --no-headers; kubectl get nodes --no-headers | awk '{print "node", $2, $5}'; } > "$out/03-drop-in.txt" 2>&1
say "infra/build-images.sh (Docker layer cache; imports the box image into the new containerd)"; infra/build-images.sh > "$out/04-build-images.log" 2>&1; say "rc=$?"
say "infra/setup-lab.sh with the dummy key"; printf 'dummy-not-a-key' | infra/setup-lab.sh > "$out/05-setup-lab.log" 2>&1; say "rc=$?"
for ns in ci-agent ci-exec ci-prep; do kubectl get ns $ns > /dev/null 2>&1 || say "namespace $ns missing"; done
python3 - > "$out/plan.json" <<'PY'
import json
print(json.dumps({"concurrency": 2, "pods": [{"name": f"c-{s}-g", "kind": k, "runtime": "kata", "gate": True, "seconds": 6, "interval": 0.1, "timeout": 0.15}
      for k, s in (("exec-repro", "exec"), ("agent", "agent"), ("prep", "prep"), ("exec-validate", "val"))]}))
PY
say "one gated Kata pod per kind"; python3 ~/net/controls/run-watch-pods.py "$run" gobwas-ws-a567dfd6 "$out/pods" ~/lab/results/patches/v1/v1-e88f0806-r1.diff "$out/plan.json" > "$out/06-pods-driver.log" 2>&1; say "rc=$?"
{ for f in "$out"/pods/c-*-g.log; do n=$(basename "$f" .log); echo "$n: $(head -1 "$f" | grep -o '"status": {[^}]*}') $(head -1 "$f" | grep -o '"kernel": "[^"]*"') | gate: $(grep -o 'NETGATE.*' "$out/pods/$n.init-netgate.log" | head -1) | forbidden tries established: $(grep '^A ' "$f" | awk '$4=="o" && $7=="st=1"' | grep -v -e ' gwm ' -e ' gwpm ' -e ' pub o' -e ' dns o' | wc -l)"; done; } > "$out/07-pods-summary.txt" 2>&1
cat "$out/07-pods-summary.txt"; say "C_DONE"
