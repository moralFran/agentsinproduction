#!/usr/bin/env bash
# Sourced by the runners. validate <pod-name> <baseline|maintainer|patch> [patch-file] -> prints the validation JSON.
# One fresh pod per check: Kata, no network (namespace lab-validate denies all), no token, a hard deadline.
validate() {
  local name="$1" mode="$2" pf="${3:-}" args="\"$2\"" vol="" mount=""
  kubectl -n lab-validate delete pod "$name" --ignore-not-found >/dev/null 2>&1
  kubectl -n lab-validate delete configmap "$name" --ignore-not-found >/dev/null 2>&1
  if [ -n "$pf" ]; then
    kubectl -n lab-validate create configmap "$name" --from-file=patch.diff="$pf" >/dev/null
    args="\"patch\", \"/in/patch.diff\""; mount='"volumeMounts":[{"name":"in","mountPath":"/in"}],'; vol='"volumes":[{"name":"in","configMap":{"name":"'$name'"}}],'
  fi
  kubectl -n lab-validate run "$name" --image=aip-validator:3 --image-pull-policy=Never --restart=Never --overrides='{"spec":{'"$vol"'"automountServiceAccountToken":false,"activeDeadlineSeconds":900,"runtimeClassName":"kata-qemu","containers":[{"name":"v","image":"aip-validator:3","imagePullPolicy":"Never",'"$mount"'"command":["python3","/validator/validate.py",'"$args"']}]}}' >/dev/null
  kubectl -n lab-validate wait --for=jsonpath='{.status.phase}'=Succeeded pod/"$name" --timeout=960s >/dev/null 2>&1 || true
  kubectl -n lab-validate logs "$name" 2>/dev/null | grep '^VALIDATION ' | sed 's/^VALIDATION //'
  kubectl -n lab-validate delete pod "$name" --wait=false >/dev/null 2>&1; kubectl -n lab-validate delete configmap "$name" --ignore-not-found >/dev/null 2>&1
}
