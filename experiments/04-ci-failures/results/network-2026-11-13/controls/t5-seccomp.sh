#!/usr/bin/env bash
# T5 (2026-11-13), runs ON the VM. Turns guest seccomp on for the kata-qemu runtime through the kata-deploy chart's own
# per-shim drop-in (shims.qemu.dropIn -> config.d/50-user-overrides.toml), the same thing infra/install-k3s-kata.sh now
# passes at install time, and records what is on disk before and after. usage: t5-seccomp.sh <out-dir>
export KUBECONFIG=~/.kube/config; out="$1"; mkdir -p "$out"; K=/opt/kata/share/defaults/kata-containers/runtimes/qemu
{ echo "== $(date -u +%FT%TZ) before"
  sudo grep -n "disable_guest_seccomp" $K/configuration-qemu.toml; echo "config.d: $(sudo ls -la $K/config.d | tail -n +2 | awk '{print $5, $6, $7, $8, $9}' | tr '\n' ';')"
  sudo sha256sum $K/configuration-qemu.toml
  kubectl get runtimeclass kata-qemu -o jsonpath='{.handler}{"\n"}'; sudo grep -rn -A4 "kata-qemu\]" /var/lib/rancher/k3s/agent/etc/containerd/ 2>/dev/null | grep -i -e "kata-qemu\]" -e ConfigPath -e runtime_type | head -8
  printf '%s\n' 'shims:' '  qemu:' '    dropIn: |' '      [runtime]' '      disable_guest_seccomp = false' > "$out/kata-values.yaml"; cat "$out/kata-values.yaml"
  echo "== $(date -u +%FT%TZ) helm upgrade (same chart version, values reused plus the drop-in)"
  helm -n kube-system upgrade kata-deploy oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy --version 4.3.1 --reuse-values -f "$out/kata-values.yaml" --wait --timeout 8m 2>&1 | tail -6
  echo "== $(date -u +%FT%TZ) after"
  kubectl -n kube-system get pods --no-headers | grep kata-deploy | awk '{print $1, $3, $5}'
  sudo grep -n "disable_guest_seccomp" $K/configuration-qemu.toml; sudo sha256sum $K/configuration-qemu.toml
  echo "config.d: $(sudo ls -la $K/config.d | tail -n +2 | awk '{print $5, $6, $7, $8, $9}' | tr '\n' ';')"
  for f in $(sudo ls $K/config.d); do echo "--- $K/config.d/$f"; sudo cat "$K/config.d/$f"; done
  until kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done; kubectl get nodes --no-headers | awk '{print $2, $5}'
  echo "== $(date -u +%FT%TZ) done"; } > "$out/00-enable-guest-seccomp.log" 2>&1
tail -14 "$out/00-enable-guest-seccomp.log"
