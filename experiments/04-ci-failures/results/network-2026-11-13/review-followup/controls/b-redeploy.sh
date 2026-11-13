#!/usr/bin/env bash
# Review follow-up (2026-11-13), runs ON the VM: copies the three changed files (unpacked in /tmp/bf) into the run folder and
# the lab copy and redeploys with infra/setup-lab.sh and the DUMMY key. usage: b-redeploy.sh <run-dir> <out-dir>
export KUBECONFIG=~/.kube/config; run="$1"; out="$2"; mkdir -p "$out" /tmp/bf; tar xzf /tmp/bfiles.tgz -C /tmp/bf
{ echo "$(date -u +%FT%TZ)"; kubectl get nodes --no-headers | awk '{print "node", $2, $5}'; cd "$run"
  for f in cases/attempt.sh cases/validate.py gateway/gateway.py cases/pod.py cases/prep.py; do
    echo "before:  $(sha256sum "$f")"; cp "/tmp/bf/$f" "$f"; cp "/tmp/bf/$f" ~/lab/"$f"; echo "working tree copy: $(sha256sum "$f")"; done
  chmod +x cases/attempt.sh
  printf 'dummy-not-a-key' | infra/setup-lab.sh; echo "setup-lab.sh rc=$?"
  echo "gateway.py in ci-gateway ConfigMap: $(kubectl -n ci-gateway get configmap gateway-code -o jsonpath='{.data.gateway\.py}' | sha256sum | cut -c1-64) (compare: $(python3 -c 'import hashlib,sys; print(hashlib.sha256(open("gateway/gateway.py","rb").read().rstrip(b"\n")).hexdigest())') without the final newline)"
  kubectl -n ci-gateway get pods --no-headers | awk '{print $1, $2, $3}'
  echo "provider key in the Secret is the dummy: $(kubectl -n ci-gateway get secret gateway-key -o jsonpath='{.data.key}' | base64 -d | grep -c '^dummy-not-a-key$')"
  echo "$(date -u +%FT%TZ)"; } > "$out/00-redeploy.log" 2>&1
tail -6 "$out/00-redeploy.log"
