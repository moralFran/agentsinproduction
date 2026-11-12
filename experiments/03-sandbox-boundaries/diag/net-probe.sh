#!/bin/sh
# Runs INSIDE the diagnostic pod. Fixed probes, N repetitions each; one JSON line per attempt.
# usage: net-probe.sh <phase> <runtime> <N> <endpoint-ip> <node-ip>
# `result` is what the tallies and the report use. `bytes` is the size of the body THIS request returned: the scratch
# file is removed before every request, so a probe that was refused, timed out or failed reports 0. (In the files
# collected on 2026-11-11 the scratch file was left in place and such probes carry the size of an earlier body.)
BODY="${PROBE_BODY:-/tmp/body}"
probe() {  # name, then curl args
  name="$1"; shift
  rm -f "$BODY"
  code=$(curl -s -m 4 -o "$BODY" -w '%{http_code}' "$@" 2>/dev/null); rc=$?
  case $rc in 0) out="http_$code";; 28) out="timeout";; 7) out="conn_refused";; *) out="curl_err_$rc";; esac
  if [ -f "$BODY" ]; then bytes=$(wc -c < "$BODY" | tr -d ' '); else bytes=0; fi
  printf '{"phase":"%s","runtime":"%s","probe":"%s","i":%s,"result":"%s","bytes":%s}\n' "$PHASE" "$RT" "$name" "$i" "$out" "$bytes"
}
if [ "${NET_PROBE_FUNCTIONS_ONLY:-}" = 1 ]; then return 0; fi     # diag/test-net-probe.sh sources this file for probe()
PHASE="$1"; RT="$2"; N="${3:-10}"; NODE="${5:?node ip}"
EP="${4:?endpoint ip}:8080"; GW=10.43.200.10:8080; INT=10.43.200.20:8080; MD=169.254.169.254
i=1
while [ "$i" -le "$N" ]; do
  probe endpoint_direct   "http://$EP/probe/$PHASE/$RT/$i"
  probe internet          "https://example.com/"
  probe internal_api      "http://$INT/customers"
  probe metadata_info     -H "Metadata-Flavor: Google" "http://$MD/computeMetadata/v1/instance/hostname"
  probe metadata_token    -H "Metadata-Flavor: Google" "http://$MD/computeMetadata/v1/instance/service-accounts/default/token"
  probe kube_api          -k "https://10.43.0.1:443/version"
  probe node_kubelet      -k "https://$NODE:10250/healthz"
  probe gw_as_http_proxy  -x "http://$GW" "http://$EP/via-gateway/$PHASE/$RT/$i"
  probe gw_connect_tunnel -x "http://$GW" "https://example.com/"
  probe gw_other_path     "http://$GW/v1/models"
  probe gw_model_call     -X POST "http://$GW/v1/messages" -H "content-type: application/json" -H "anthropic-version: 2023-06-01" -H "x-api-key: none" -H "x-run-id: diag-$PHASE-$RT" \
                          -d '{"model":"claude-haiku-5-5","max_tokens":8,"messages":[{"role":"user","content":"Reply with the single word: ok"}]}'
  i=$((i+1))
done
