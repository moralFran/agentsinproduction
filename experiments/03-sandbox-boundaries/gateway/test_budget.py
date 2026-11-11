#!/usr/bin/env python3
"""Offline test of the gateway's budget and request format, against a fake upstream (no provider call, no key).
The budget works on ESTIMATED reservations (see gateway.py); these checks show the mechanism, not a money guarantee.
 1. A call whose reservation would pass the budget is refused before it is forwarded.
 2. Restarting the gateway does not reset what was spent.
 3. Many simultaneous calls: the reservations together cannot pass the budget.
 4. The process is KILLED while a call is in flight: after the restart that call counts in full, and a call that would
    only fit if it had been free is refused.
 5. The state cannot be written: nothing is forwarded (503). A state file that cannot be read: the gateway won't start.
 6. Requests outside the allowed format (image by URL, document, server tool, cache_control, the thinking parameter,
    unknown field) are refused and never forwarded; the agent's own tool loop, including a thinking block the model
    returned and the agent sends back, is accepted.
 7. A response that costs more than its reservation halts the gateway (that call already happened; the next are refused).
 8. Price tiers by prompt length (the provider's long-prompt prices): a request whose estimated input is over the
    threshold is reserved at the long prices; a response whose reported prompt is over the threshold is booked at the
    long prices on all of its tokens."""
import json, os, signal, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__)); calls = []
class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        calls.append(body); time.sleep(3 if body.get("system") == "slow" else 0.2)
        tin = {"huge": 10 ** 9, "long": 150}.get(body.get("system"), 10)
        out = json.dumps({"usage": {"input_tokens": tin, "output_tokens": body["max_tokens"]}}).encode()   # uses all it may
        try: self.send_response(200); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
        except OSError: pass
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 18081), Fake).serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp(); open(f"{tmp}/key", "w").write("fake"); sdir = f"{tmp}/state"; os.mkdir(sdir); SF = f"{sdir}/budget.json"
def start(budget, wait=True):
    env = dict(os.environ, UPSTREAM="http://127.0.0.1:18081/v1/messages", KEY_FILE=f"{tmp}/key", STATE_FILE=SF, OVERHEAD_TOK="0",
               PRICES='{"m": [1000000, 1000000], "t": [1000000, 1000000, 100, 5000000, 5000000]}', BUDGET_USD=str(budget), PORT="18080")      # $1 per token: money == tokens
    p = subprocess.Popen([sys.executable, f"{HERE}/gateway.py"], env=env, stdout=subprocess.DEVNULL)
    for _ in range(50):
        if not wait or p.poll() is not None: break
        try: urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=1); break
        except Exception: time.sleep(0.1)
    return p
def stop(p): p.terminate(); p.wait()
def post(body):
    try: return urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18080/v1/messages", data=json.dumps(body).encode()), timeout=10).status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return type(e).__name__
def call(max_tokens, **kw): return post({"model": "m", "max_tokens": max_tokens, "messages": [], **kw})
def reset():
    calls.clear()
    if os.path.exists(SF): os.remove(SF)
spent = lambda: json.load(open(SF))["spent_usd"]
ok = True
def check(name, cond, detail):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), name, *(() if "--short" in sys.argv else ("-", detail)), flush=True)
size = lambda **kw: len(json.dumps({"model": "m", "max_tokens": 8, "messages": [], **kw}).encode())   # input bound, in tokens
one = size() + 8                                      # bound of one call

p = start(budget=one + 17)                            # fits one call; after its real usage (18) is booked, one more would pass the cap by 1
a = call(8); b = call(8)
check("1 a call whose reservation would pass the budget is refused", a == 200 and b == 429 and len(calls) == 1, f"first {a}, second {b}, forwarded {len(calls)}, spent {spent():.0f} of cap {one + 17}")
stop(p); calls.clear()
p = start(budget=one + 17); c = call(8)
check("2 restart keeps the spent amount", c == 429 and len(calls) == 0 and spent() == 18, f"after restart: status {c}, forwarded {len(calls)}, spent {spent():.0f}")
stop(p); reset()

cap = 5 * one + 3                                     # the bound of exactly 5 calls fits
p = start(budget=cap); res = []
ts = [threading.Thread(target=lambda: res.append(call(8))) for _ in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
check("3 20 simultaneous calls: reservations cannot pass the budget", res.count(200) == 5 and len(calls) == 5 and spent() <= cap, f"{res.count(200)} forwarded, {res.count(429)} refused, spent {spent():.0f} of cap {cap}")
stop(p); reset()

slow = size(system="slow") + 8; cap = slow + one - 1  # the slow call's bound fits; a second call fits only if the slow one were free
p = start(budget=cap)
t = threading.Thread(target=lambda: call(8, system="slow")); t.start(); time.sleep(1.0)
on_disk = json.load(open(SF))
p.send_signal(signal.SIGKILL); p.wait(); t.join()     # dies after forwarding, before any response
p = start(budget=cap); d = call(8)
check("4 killed mid-call: the reservation was on disk and survives", len(on_disk["reserved"]) == 1 and d == 429 and len(calls) == 1 and spent() == slow,
      f"reserved on disk before the kill: {sum(on_disk['reserved'].values()):.0f}; after restart: status {d}, forwarded {len(calls)} (only the killed one), spent {spent():.0f} of cap {cap}")
stop(p); reset()

p = start(budget=10 * one); os.chmod(sdir, 0o500)     # the state directory becomes read-only
e = call(8); os.chmod(sdir, 0o700); f = call(8)
check("5a state cannot be written: nothing is forwarded", e == 503 and f == 200 and len(calls) == 1, f"read-only state: status {e}; writable again: status {f}; forwarded {len(calls)}")
stop(p); calls.clear(); open(SF, "w").write("{not json")
p = start(budget=10 * one, wait=False); rc = p.wait(timeout=10)
check("5b unreadable state file: the gateway does not start", rc != 0, f"exit code {rc}")
reset()

p = start(budget=10 ** 7)
img = {"type": "image", "source": {"type": "url", "url": "http://example.invalid/big.png"}}
bad = {
  "image by URL": dict(messages=[{"role": "user", "content": [img]}]),
  "image inside a tool result": dict(messages=[{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [img]}]}]),
  "document by file id": dict(messages=[{"role": "user", "content": [{"type": "document", "source": {"type": "file", "file_id": "file_x"}}]}]),
  "server tool": dict(tools=[{"type": "web_search_20260209", "name": "web_search"}]),
  "cache_control on a block": dict(messages=[{"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}]}]),
  "system as blocks": dict(system=[{"type": "text", "text": "x", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]),
  "thinking parameter": dict(thinking={"type": "adaptive"}),
  "thinking block in a user turn": dict(messages=[{"role": "user", "content": [{"type": "thinking", "thinking": "x", "signature": "s"}]}]),
  "mcp servers": dict(mcp_servers=[{"type": "url", "url": "http://example.invalid/mcp", "name": "x"}]),
  "streaming": dict(stream=True),
}
got = {k: call(8, **v) for k, v in bad.items()}
check("6a requests outside the allowed format are refused, none forwarded", all(v == 403 for v in got.values()) and len(calls) == 0, f"{sum(v == 403 for v in got.values())}/{len(got)} refused with 403, forwarded {len(calls)}" + "".join(f"; {k}: {v}" for k, v in got.items() if v != 403))
loop = dict(system="s", tools=[{"name": "bash", "description": "d", "input_schema": {"type": "object"}}], messages=[
  {"role": "user", "content": "start"},
  {"role": "assistant", "content": [{"type": "thinking", "thinking": "plan", "signature": "c2ln"}, {"type": "text", "text": "running", "citations": None}, {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}]},
  {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "exit code 0\nfile"}]}])
g = call(8, **loop)
check("6b the agent's own tool loop is accepted", g == 200 and len(calls) == 1, f"status {g}, forwarded {len(calls)}")
stop(p); reset()

p = start(budget=10 ** 12); h = call(8, system="huge"); i = call(8); st = json.load(open(SF))
check("7 a response above its reservation halts the gateway", h == 200 and i == 503 and len(calls) == 1 and st["halted"], f"first {h}, next {i}, forwarded {len(calls)}, halted: {st['halted']}")
stop(p); reset()

tcall = lambda mt, **kw: post({"model": "t", "max_tokens": mt, "messages": [], **kw})
tsize = lambda **kw: len(json.dumps({"model": "t", "max_tokens": 8, "messages": [], **kw}).encode())
pad = "x" * 100; big = tsize(system=pad)             # estimated input over the 100-token threshold
cap = 3 * (big + 8)                                   # would fit at the base price (1x), not at the long price (5x)
p = start(budget=cap); j = tcall(8, system=pad)
check("8a estimated input over the threshold is reserved at the long price", j == 429 and len(calls) == 0, f"status {j}, forwarded {len(calls)}: reservation {5 * (big + 8)} at the long price vs cap {cap} (base price would be {big + 8})")
stop(p); reset()
p = start(budget=10 ** 6); k = tcall(8, system="long"); st = json.load(open(SF)); l = tcall(8)
check("8b reported prompt over the threshold is booked at the long price", k == 200 and st["spent_usd"] == 5 * (150 + 8) and l == 503, f"upstream reported 150 prompt tokens: booked {st['spent_usd']:.0f} (base price would be {150 + 8}); it exceeded its reservation {tsize(system='long') + 8}, next call {l}")
stop(p)
sys.exit(0 if ok else 1)
