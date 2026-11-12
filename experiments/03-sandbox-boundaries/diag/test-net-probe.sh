#!/usr/bin/env bash
# Offline test of probe() in net-probe.sh: `bytes` belongs to the request that reports it. Only 127.0.0.1 is
# contacted: a local server (a 543-byte body; a path that never answers) and a closed local port. About 5 s.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; tmp="$(mktemp -d)"; srv=""
trap '[ -z "$srv" ] || kill "$srv" 2>/dev/null; rm -rf "$tmp"' EXIT
python3 - "$tmp/ports" <<'PY' &
import socket, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/never": time.sleep(30); return
        body = b"x" * 543
        self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
s = ThreadingHTTPServer(("127.0.0.1", 0), H)
c = socket.socket(); c.bind(("127.0.0.1", 0)); closed = c.getsockname()[1]; c.close()      # a port nothing listens on
open(sys.argv[1], "w").write(f"{s.server_address[1]} {closed}\n"); s.serve_forever()
PY
srv=$!
for _ in $(seq 50); do [ -s "$tmp/ports" ] && break; sleep 0.1; done
read -r port closed < "$tmp/ports"
PHASE=test; RT=offline; i=1; PROBE_BODY="$tmp/body"; NET_PROBE_FUNCTIONS_ONLY=1
# shellcheck source=/dev/null
. "$here/net-probe.sh"
{ probe answered "http://127.0.0.1:$port/"; probe refused "http://127.0.0.1:$closed/"; probe no_answer "http://127.0.0.1:$port/never"; probe answered_again "http://127.0.0.1:$port/"; } > "$tmp/out"
python3 - "$tmp/out" <<'PY'
import json, sys
rows = {r["probe"]: r for r in map(json.loads, open(sys.argv[1]))}
want = {"answered": ("http_200", 543), "refused": ("conn_refused", 0), "no_answer": ("timeout", 0), "answered_again": ("http_200", 543)}
ok = True
for name, (result, size) in want.items():
    r = rows.get(name, {}); good = (r.get("result"), r.get("bytes")) == (result, size); ok &= good
    print("PASS" if good else "FAIL", f"{name}: result {r.get('result')}, bytes {r.get('bytes')} (expected {result}, {size})")
sys.exit(0 if ok else 1)
PY
