#!/usr/bin/env python3
"""Fake internal service with dummy data. Stands in for "the company's other systems" next to the agent."""
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
CUSTOMERS = [{"id": i, "name": f"Dummy Customer {i}", "email": f"customer{i}@example.invalid", "plan": "starter"} for i in range(1, 6)]
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        print(json.dumps({"ts": time.time(), "from": self.client_address[0], "path": self.path}), flush=True)
        out = json.dumps({"service": "billing-internal (fake)", "customers": CUSTOMERS}).encode()
        self.send_response(200); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
