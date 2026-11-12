#!/usr/bin/env bash
# Sourced by the runners. validate <pod-name> <baseline|maintainer|patch> [patch-file] -> prints the validation JSON.
# One fresh pod per check, from k8s/71-validator-pod.yaml: Kata, no network (namespace lab-validate denies all), no
# token, non-root, read-only root filesystem, limits, a hard deadline. The pod gets a nonce made here; the verdict is
# the last line `VALIDATION <nonce> <json>` of its log, and no such line means no verdict (the callers treat that as
# invalid). The wait ends when the pod Succeeded or Failed.
_aip_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$_aip_root/infra/pod-wait.sh"
validate() {
  local name="$1" mode="$2" pf="${3:-}" args nonce empty=""
  if [ "$mode" = patch ]; then args='["python3", "/validator/validate.py", "patch", "/in/patch.diff"]'
  else args='["python3", "/validator/validate.py", "'"$mode"'"]'; empty="$(mktemp)"; pf="$empty"; fi
  nonce="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  kubectl -n lab-validate delete pod "$name" --ignore-not-found >/dev/null 2>&1
  kubectl -n lab-validate delete configmap "$name" --ignore-not-found >/dev/null 2>&1
  kubectl -n lab-validate create configmap "$name" --from-file=patch.diff="$pf" >/dev/null
  sed -e "s|POD_NAME|$name|g" -e "s|VALIDATOR_ARGS|$args|" -e "s|NONCE_VALUE|$nonce|" "$_aip_root/k8s/71-validator-pod.yaml" | kubectl apply -f - >/dev/null
  pod_done lab-validate "$name" 960
  kubectl -n lab-validate logs "$name" -c v 2>/dev/null | grep "^VALIDATION $nonce " | tail -1 | sed "s/^VALIDATION $nonce //"
  kubectl -n lab-validate delete pod "$name" --wait=false >/dev/null 2>&1; kubectl -n lab-validate delete configmap "$name" --ignore-not-found >/dev/null 2>&1
  [ -z "$empty" ] || rm -f "$empty"
}
