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
    long prices on all of its tokens.
Fourth review (the clients are untrusted; see "Connections" and "Upstream" in gateway.py):
 9. A Content-Length that is not one decimal number, a model that is not a string, a max_tokens that is not a finite
    number: 400, nothing forwarded, the gateway keeps answering.
10. A request that does not arrive within the deadline is cut, however it stalls: body never completed (408), body
    trickling in byte by byte (408 at the total deadline, not per byte), headers never completed (closed). Stalled
    connections cannot pass the limit per source address: the next connection is told 503 at once.
11. The upstream answers 302: the gateway answers 502 and the second host receives nothing (so no key).
12. The upstream always gets the gateway's own anthropic-version and key; the client's headers are not forwarded.
GATEWAY_PY=<path> runs the same checks against another copy of the gateway (used once against the pre-review code)."""
import json, os, signal, socket, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__)); calls = []; seen = []; elsewhere = []
GATEWAY_PY = os.environ.get("GATEWAY_PY", f"{HERE}/gateway.py")
class Elsewhere(BaseHTTPRequestHandler):                # the host a redirect points to: it must never be called
    def _any(self):
        elsewhere.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200); self.send_header("content-length", "2"); self.end_headers(); self.wfile.write(b"{}")
    do_GET = do_POST = _any
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 18082), Elsewhere).serve_forever, daemon=True).start()
class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        calls.append(body); seen.append({k.lower(): v for k, v in self.headers.items()})
        if body.get("system") == "redirect":
            self.send_response(302); self.send_header("location", "http://127.0.0.1:18082/v1/messages")
            self.send_header("content-length", "0"); self.end_headers(); return
        time.sleep(3 if body.get("system") == "slow" else 0.2)
        tin = {"huge": 10 ** 9, "long": 150}.get(body.get("system"), 10)
        out = json.dumps({"usage": {"input_tokens": tin, "output_tokens": body["max_tokens"]}}).encode()   # uses all it may
        try: self.send_response(200); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
        except OSError: pass
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 18081), Fake).serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp(); open(f"{tmp}/key", "w").write("fake"); sdir = f"{tmp}/state"; os.mkdir(sdir); SF = f"{sdir}/budget.json"
def start(budget, wait=True, **extra):
    env = dict(os.environ, UPSTREAM="http://127.0.0.1:18081/v1/messages", KEY_FILE=f"{tmp}/key", STATE_FILE=SF, OVERHEAD_TOK="0",
               PRICES='{"m": [1000000, 1000000], "t": [1000000, 1000000, 100, 5000000, 5000000]}', BUDGET_USD=str(budget), PORT="18080",      # $1 per token: money == tokens
               **{"MAX_CONN_PER_SOURCE": "64", **extra})  # every client here is 127.0.0.1; the limit per source has its own check (10d)
    p = subprocess.Popen([sys.executable, GATEWAY_PY], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if not wait or p.poll() is not None: break
        try: urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=1); break
        except Exception: time.sleep(0.1)
    return p
def stop(p): p.terminate(); p.wait()
def post(body, headers={}):
    try: return urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18080/v1/messages", data=json.dumps(body).encode(), headers=headers), timeout=10).status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return type(e).__name__
def call(max_tokens, **kw): return post({"model": "m", "max_tokens": max_tokens, "messages": [], **kw})
def raw(head, trickle=b"", every=0.25, wait=6.0):
    """Sends raw bytes (then `trickle` one byte at a time), reads until the gateway answers or closes or `wait` passes.
    -> (status line, or "closed" / "no answer", seconds)."""
    t = time.time(); buf = b""; state = "no answer"
    try:
        s = socket.create_connection(("127.0.0.1", 18080), timeout=2); s.sendall(head); s.settimeout(every); rest = trickle
        while time.time() - t < wait:
            try:
                c = s.recv(65536)
                if not c: state = "closed"; break
                buf += c
            except socket.timeout:
                if rest:
                    try: s.sendall(rest[:1])
                    except OSError: pass
                    rest = rest[1:]
            except OSError: state = "closed"; break
        s.close()
    except OSError: state = "closed"
    return (buf.split(b"\r\n", 1)[0].decode(errors="replace") if buf else state), time.time() - t
def reset():
    calls.clear(); seen.clear(); elsewhere.clear()
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
stop(p); reset()

REQ = "POST /v1/messages HTTP/1.1\r\nHost: gateway\r\nContent-Type: application/json\r\n"
valid = json.dumps({"model": "m", "max_tokens": 8, "messages": []})
p = start(budget=10 ** 7)
bad_cl = {"not a number": "Content-Length: abc\r\n", "negative": "Content-Length: -5\r\n", "exponent": "Content-Length: 1e3\r\n", "two numbers": "Content-Length: 12 13\r\n",
          "superscript digit": "Content-Length: \u00b2\r\n", "missing": "", "zero": "Content-Length: 0\r\n", "sent twice": f"Content-Length: {len(valid)}\r\nContent-Length: {len(valid) + 1}\r\n",
          "chunked instead": "Transfer-Encoding: chunked\r\n"}
got = {k: raw((REQ + v + "\r\n" + valid).encode("latin-1"))[0] for k, v in bad_cl.items()}
big = raw((REQ + "Content-Length: 4000001\r\n\r\n").encode())[0]; after = call(8)
check("9a a bad Content-Length is answered 400 (too large: 413), nothing forwarded", all(" 400 " in v for v in got.values()) and " 413 " in big and after == 200 and len(calls) == 1,
      f"{sum(' 400 ' in v for v in got.values())}/{len(got)} answered 400, 4,000,001 bytes: {big[9:12]}, a valid call afterwards: {after}, forwarded {len(calls)}" + "".join(f"; {k}: {v}" for k, v in got.items() if " 400 " not in v))
calls.clear()
bad_body = {"model is a list": dict(model=["m"]), "model is an object": dict(model={"m": 1}), "model is a number": dict(model=5), "model is null": dict(model=None),
            "max_tokens is Infinity": dict(max_tokens=float("inf")), "max_tokens is a list": dict(max_tokens=[8]), "max_tokens is text": dict(max_tokens="many")}
got = {k: post({"model": "m", "max_tokens": 8, "messages": [], **v}) for k, v in bad_body.items()}; after = call(8)
check("9b a model or max_tokens of the wrong type is answered 400, nothing forwarded", all(v == 400 for v in got.values()) and after == 200 and len(calls) == 1,
      f"{sum(v == 400 for v in got.values())}/{len(got)} answered 400, a valid call afterwards: {after}, forwarded {len(calls)}" + "".join(f"; {k}: {v}" for k, v in got.items() if v != 400))
stop(p); reset()

D = 2.0; within = lambda s: D - 0.5 <= s <= D + 2.0   # the deadline of these checks, and "cut at the deadline"
p = start(budget=10 ** 7, READ_DEADLINE_S=str(D), MAX_CONN_PER_SOURCE="4")
a, sa = raw((REQ + "Content-Length: 1000\r\n\r\n" + valid[:10]).encode())
check("10a a body that never completes is cut at the deadline", " 408 " in a and within(sa) and len(calls) == 0, f"10 of 1,000 bytes sent, then silence: {a[9:] or a} after {sa:.1f} s (deadline {D:.0f} s), forwarded {len(calls)}")
b, sb = raw((REQ + "Content-Length: 1000\r\n\r\n").encode(), trickle=b"x" * 1000, every=0.25)
check("10b a body trickling in is cut at the same total deadline", " 408 " in b and within(sb) and len(calls) == 0, f"one byte every 0.25 s: {b[9:] or b} after {sb:.1f} s, forwarded {len(calls)}")
c, sc = raw(REQ.encode())
check("10c headers that never complete: the connection is closed at the deadline", c == "closed" and within(sc), f"{c} after {sc:.1f} s")
idle = [socket.create_connection(("127.0.0.1", 18080), timeout=2) for _ in range(4)]; time.sleep(0.3)
d, sd = raw(b"", wait=3.0); time.sleep(D + 0.7); after = call(8)
check("10d stalled connections cannot pass the limit per source", " 503 " in d and sd < 1.0 and after == 200 and len(calls) == 1,
      f"4 idle connections open (the limit here), the 5th: {d[9:] or d} after {sd:.1f} s; once they are cut at the deadline, a valid call: {after}")
[s.close() for s in idle]; stop(p); reset()

p = start(budget=10 ** 7); e = call(8, system="redirect"); st = json.load(open(SF)); after = call(8)
check("11 an upstream redirect is refused: the second host receives nothing", e == 502 and len(elsewhere) == 0 and len(calls) == 2 and st["spent_usd"] == 0 and not st["reserved"] and after == 200,
      f"upstream answered 302: status {e}, requests received by the redirect target: {len(elsewhere)}" + (f" (x-api-key sent to it: {'x-api-key' in elsewhere[0]})" if elsewhere else "") + f", booked {st['spent_usd']:.0f}, next call {after}")
reset()
f = post({"model": "m", "max_tokens": 8, "messages": []}, headers={"anthropic-version": "1999-01-01", "anthropic-beta": "anything", "x-api-key": "from-the-client", "authorization": "Bearer from-the-client"})
h = seen[0] if seen else {}
check("12 the version header and the key are the gateway's own", f == 200 and h.get("anthropic-version") == "2023-06-01" and h.get("x-api-key") == "fake" and "anthropic-beta" not in h and "authorization" not in h,
      f"client sent anthropic-version 1999-01-01, a beta header and its own key; upstream saw version {h.get('anthropic-version')}, key from the gateway: {h.get('x-api-key') == 'fake'}, beta header: {'anthropic-beta' in h}, authorization: {'authorization' in h}")
stop(p)
sys.exit(0 if ok else 1)
