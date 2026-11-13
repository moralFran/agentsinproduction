#!/usr/bin/env bash
# T7 (2026-11-13), runs ON the VM. Copies the four changed files (unpacked in /tmp/t7f) into the fresh run folder and the lab
# copy, then redeploys the way the follow-up round did: infra/setup-lab.sh with the DUMMY key on stdin (it re-applies the
# manifests, reloads the gateway code ConfigMap, restarts the gateway and calls infra/code-configmap.sh).
# usage: t7-redeploy.sh <run-dir> <out-dir>
export KUBECONFIG=~/.kube/config; run="$1"; out="$2"; mkdir -p "$out" /tmp/t7f; tar xzf /tmp/t7files.tgz -C /tmp/t7f
{ echo "$(date -u +%FT%TZ)"; cd "$run"
  for f in gateway/gateway.py cases/attempt.sh agent/agent.py executor/executor.py; do
    echo "before:  $(sha256sum "$f")"; cp "/tmp/t7f/$f" "$f"; cp "/tmp/t7f/$f" ~/lab/"$f"; echo "working tree copy: $(sha256sum "$f")"; done
  chmod +x cases/attempt.sh
  printf 'dummy-not-a-key' | infra/setup-lab.sh; echo "setup-lab.sh rc=$?"
  echo "agent.py in ci-agent ConfigMap:     $(kubectl -n ci-agent get configmap ci-code -o jsonpath='{.data.agent\.py}' | sha256sum | cut -c1-64)"
  echo "executor.py in ci-exec ConfigMap:   $(kubectl -n ci-exec get configmap ci-code -o jsonpath='{.data.executor\.py}' | sha256sum | cut -c1-64)"
  echo "gateway.py in ci-gateway ConfigMap: $(kubectl -n ci-gateway get configmap gateway-code -o jsonpath='{.data.gateway\.py}' | sha256sum | cut -c1-64)"
  echo "(the jsonpath output has no trailing newline difference: compare with the sums above)"
  kubectl -n ci-gateway get pods -o wide --no-headers | awk '{print $1, $2, $3, $6}'
  echo "provider key in the Secret is the dummy: $(kubectl -n ci-gateway get secret gateway-key -o jsonpath='{.data.key}' | base64 -d | grep -c '^dummy-not-a-key$')"
  echo "$(date -u +%FT%TZ)"; } > "$out/00-redeploy.log" 2>&1
tail -8 "$out/00-redeploy.log"
