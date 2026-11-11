#!/usr/bin/env python3
"""Test endpoint we control (runs on aip-endpoint-01). Answers every request and logs it as one JSON line.
Stands in for "somewhere on the outside" a command might try to send data to. Holds no real data."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def _any(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        print(json.dumps({"ts": time.time(), "from": self.client_address[0], "method": self.command, "path": self.path,
                          "bytes": len(body)}), flush=True)
        out = b"endpoint-ok\n"
        self.send_response(200); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    do_GET = do_POST = do_PUT = _any
    def log_message(self, *a): pass

ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8080), H).serve_forever()
