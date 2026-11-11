#!/bin/sh
# Runs INSIDE an RBAC-lab pod. 10 reads of the dummy Secret with the pod's own token, plus controls.
ID="$1"; N="${2:-10}"; API=https://10.43.0.1:443; T=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
one() { name="$1"; tok="$2"; url="$3"
  code=$(curl -s -k -m 5 -o /tmp/b -w '%{http_code}' -H "Authorization: Bearer $tok" "$url"); rc=$?
  case $rc in 0) out="http_$code";; 28) out="timeout";; *) out="curl_err_$rc";; esac
  leaked=$(grep -c '"password"' /tmp/b 2>/dev/null || true)
  printf '{"identity":"%s","probe":"%s","i":%s,"result":"%s","secret_in_body":%s}\n' "$ID" "$name" "$i" "$out" "${leaked:-0}"; }
i=1; while [ "$i" -le "$N" ]; do
  one get_dummy_secret   "$T"            "$API/api/v1/namespaces/lab-rbac/secrets/dummy-credentials"
  one list_secrets       "$T"            "$API/api/v1/namespaces/lab-rbac/secrets"
  one other_ns_secret    "$T"            "$API/api/v1/namespaces/lab-gateway/secrets/gateway-key"
  one invalid_token      "not-a-token"   "$API/api/v1/namespaces/lab-rbac/secrets/dummy-credentials"
  i=$((i+1)); done
