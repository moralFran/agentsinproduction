#!/usr/bin/env python3
"""Offline test of the gateway v4 (experiment 04): the v3 checks 1-8 run unchanged inside one open run with a large cap,
plus 9 (per-run caps and run ids) and 10 (cache pricing).
Offline test of the gateway's budget and request format, against a fake upstream (no provider call, no key).
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

HERE = os.path.dirname(os.path.abspath(__file__)); calls = []; redirects = []; forwarded_headers = []; TOKENS = {}
class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        forwarded_headers.append(dict(self.headers))
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if body.get("system") == "redirect":
            calls.append(body)
            self.send_response(302); self.send_header("Location", "http://127.0.0.1:18081/redirect-target")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        calls.append(body); time.sleep(3 if body.get("system") == "slow" else 0.2)
        tin = {"huge": 10 ** 9, "long": 150}.get(body.get("system"), 10)
        usage = {"input_tokens": tin, "output_tokens": body["max_tokens"]}                                   # uses all it may
        if body.get("system") == "cached": usage = {"input_tokens": 10, "cache_creation_input_tokens": 40, "cache_read_input_tokens": 100, "output_tokens": 8}
        out = json.dumps({"usage": usage}).encode()
        try: self.send_response(200); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
        except OSError: pass
    def do_GET(self):
        redirects.append(True)
        self.send_response(418); self.send_header("Content-Length", "0"); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 18081), Fake).serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp(); open(f"{tmp}/key", "w").write("fake"); sdir = f"{tmp}/state"; os.mkdir(sdir); SF = f"{sdir}/budget.json"
open(f"{tmp}/admin-key", "w").write("fake-admin")
def start(budget, wait=True):
    env = dict(os.environ, UPSTREAM="http://127.0.0.1:18081/v1/messages", KEY_FILE=f"{tmp}/key", ADMIN_KEY_FILE=f"{tmp}/admin-key", STATE_FILE=SF, OVERHEAD_TOK="0", MAX_RUN_USD="1000000000000000", HTTP_READ_TIMEOUT_S="2",
               PRICES='{"m": [1000000, 1000000], "t": [1000000, 1000000, 100, 5000000, 5000000]}', BUDGET_USD=str(budget), PORT="18080", ADMIN_PORT="18082")      # $1 per token: money == tokens
    with open(f"{tmp}/gateway.log", "a") as log_file:
        p = subprocess.Popen([sys.executable, f"{HERE}/gateway.py"], env=env, stdout=log_file)
    for _ in range(50):
        if not wait or p.poll() is not None: break
        try: urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=1); break
        except Exception: time.sleep(0.1)
    if wait and p.poll() is None: admin("/runs", {"run": RUN, "cap_usd": 10 ** 15})
    return p
RUN = "t"
def admin(path, body=None, token="fake-admin"):
    req = urllib.request.Request("http://127.0.0.1:18082" + path, data=json.dumps(body).encode() if body is not None else None, headers={"Authorization": "Bearer " + token} if token else {})
    try:
        result = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if path == "/runs" and body is not None and "token" in result: TOKENS[body["run"]] = result["token"]
        return result
    except urllib.error.HTTPError as e: return {"status": e.code}
def stop(p): p.terminate(); p.wait()
def post(body, run=None, token=None, headers=None):
    auth = TOKENS.get(run or RUN, run or RUN) if token is None else token
    try: return urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18080/v1/messages", data=json.dumps(body).encode(), headers={"x-run-token": auth, **(headers or {})}), timeout=10).status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return type(e).__name__
def call(max_tokens, **kw): return post({"model": "m", "max_tokens": max_tokens, "messages": [], **kw})
def reset():
    calls.clear()
    TOKENS.clear(); forwarded_headers.clear()
    if os.path.exists(SF): os.remove(SF)
spent = lambda: json.load(open(SF))["spent_usd"]
ok = True
def check(name, cond, detail):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), name, *(() if "--short" in sys.argv and cond else ("-", detail)), flush=True)
size = lambda **kw: len(json.dumps({"model": "m", "max_tokens": 8, "messages": [], **kw}).encode())   # input bound, in tokens
W = 1.25                                              # v4 reserves every input token as a cache write
half = lambda n: (n + 1) // 2                         # v4 since 12/11: input estimate = request bytes / 2
one = W * half(size()) + 8                            # reservation of one call

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

slow = W * half(size(system="slow")) + 8; cap = slow + one - 1  # the slow call's bound fits; a second call fits only if the slow one were free
p = start(budget=cap)
t = threading.Thread(target=lambda: call(8, system="slow")); t.start(); time.sleep(1.0)
on_disk = json.load(open(SF))
p.send_signal(signal.SIGKILL); p.wait(); t.join()     # dies after forwarding, before any response
p = start(budget=cap); d = call(8)
check("4 killed mid-call: the reservation was on disk and survives", len(on_disk["reserved"]) == 1 and d == 429 and len(calls) == 1 and spent() == slow,
      f"reserved on disk before the kill: {sum(v['usd'] for v in on_disk['reserved'].values()):.0f}; after restart: status {d}, forwarded {len(calls)} (only the killed one), spent {spent():.0f} of cap {cap}")
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
  "cache_control with a 1-hour TTL": dict(messages=[{"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}]),
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
pad = "x" * 260; big = half(tsize(system=pad))       # estimated input (bytes / 2) over the 100-token threshold
cap = 3 * (W * big + 8)                               # would fit at the base price (1x), not at the long price (5x)
p = start(budget=cap); j = tcall(8, system=pad)
check("8a estimated input over the threshold is reserved at the long price", j == 429 and len(calls) == 0, f"status {j}, forwarded {len(calls)}: reservation {5 * (W * big + 8)} at the long price vs cap {cap} (base price would be {big + 8})")
stop(p); reset()
p = start(budget=10 ** 6); k = tcall(8, system="long"); st = json.load(open(SF)); l = tcall(8)
check("8b reported prompt over the threshold is booked at the long price", k == 200 and st["spent_usd"] == 5 * (150 + 8) and l == 503, f"upstream reported 150 prompt tokens: booked {st['spent_usd']:.0f} (base price would be {150 + 8}); it exceeded its reservation {tsize(system='long') + 8}, next call {l}")
stop(p); reset()

# 9. per-run caps: a run can spend only its own cap; unknown and closed runs are refused; reused ids are refused
p = start(budget=10 ** 9)
admin("/runs", {"run": "small", "cap_usd": one + 17}); n0 = len(calls)
a, b = post({"model": "m", "max_tokens": 8, "messages": []}, "small"), post({"model": "m", "max_tokens": 8, "messages": []}, "small")
u = post({"model": "m", "max_tokens": 8, "messages": []}, "never-opened")
admin("/runs/small/close", {}); c = post({"model": "m", "max_tokens": 8, "messages": []}, "small")
dup = admin("/runs", {"run": "small", "cap_usd": 1}); rs = admin("/runs/small")
check("9 per-run cap, unknown and closed runs, no reuse", (a, b, u, c) == (200, 429, 403, 403) and len(calls) - n0 == 1 and dup.get("status") == 409 and rs["spent_usd"] == 18,
      f"run small: {a} then {b} (cap {one + 17}, spent {rs['spent_usd']:.0f}); unknown run {u}; after close {c}; reopen same id {dup.get('status')}")
stop(p); reset()

# 10. cache pricing: 10 plain + 40 written + 100 read input tokens at $1/token, 8 output; Haiku-like read price 0.1x
p = start(budget=10 ** 9); st0 = 0
cc = post({"model": "m", "max_tokens": 8, "system": "cached", "messages": [{"role": "user", "content": [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}]}]})
hr = post({"model": "m", "max_tokens": 8, "messages": [{"role": "user", "content": [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}]})
booked = json.load(open(SF))["spent_usd"]
want = 10 + 1.25 * 40 + 1.0 * 100 + 8     # model "m" has no read multiplier listed: reads are booked at the full price (conservative)
check("10 cache writes and reads are priced; 1-hour TTL is refused", cc == 200 and hr == 403 and abs(booked - want) < 1e-6, f"5-min cache call {cc}, booked {booked} (expected {want}); 1-hour TTL {hr}")
before = json.load(open(SF))
missing = admin("/state", token=None); wrong = admin("/runs", {"run": "unauthorized", "cap_usd": 999}, token="wrong")
check("11 admin authentication rejects absent and wrong credentials without state changes",
      missing.get("status") == 401 and wrong.get("status") == 401 and json.load(open(SF)) == before,
      f"missing={missing.get('status')}, wrong={wrong.get('status')}")
invalid = [admin("/runs", {"run": "bad-cap", "cap_usd": cap}) for cap in (0, -1, float('inf'), float('nan'), 10 ** 16)]
check("12 invalid administrative run caps cannot change state", all(v.get("status") == 400 for v in invalid) and json.load(open(SF)) == before, str(invalid))
stop(p); reset(); p = start(budget=10 ** 9)  # the cache-price fixture may have halted its previous gateway
redirect_status = call(8, system="redirect")
check("13 upstream redirects are not followed", redirect_status == 302 and not redirects, f"status={redirect_status}, followed={redirects}")
import socket
with socket.create_connection(("127.0.0.1", 18080), timeout=5) as conn:
    conn.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: localhost\r\nContent-Length: 100\r\n\r\n{")
    conn.settimeout(5)
    closed = conn.recv(1) == b""
check("14 incomplete request bodies time out", closed, "slow client disconnected")
stop(p); reset()

# Public ids are labels, not credentials. A parallel run cannot borrow another open run's budget by naming it.
p = start(budget=10 ** 9)
ra = admin("/runs", {"run":"v1-public-a-r1", "cap_usd":one + 17})
rb = admin("/runs", {"run":"v1-public-b-r1", "cap_usd":10 * one})
body = {"model":"m", "max_tokens":8, "messages":[]}
first = post(body, "v1-public-a-r1", headers={"x-run-id":"v1-public-b-r1"})
responses = {}
def attempt(name, **kw): responses[name] = post(body, **kw)
threads = [threading.Thread(target=attempt, args=(name,), kwargs=kw) for name,kw in [
    ("exhausted-a", {"run":"v1-public-a-r1", "headers":{"x-run-id":"v1-public-b-r1"}}),
    ("valid-b", {"run":"v1-public-b-r1"}),
    ("public-id", {"token":"v1-public-b-r1"}),
    ("legacy-id", {"token":"", "headers":{"x-run-id":"v1-public-b-r1"}}),
    ("unknown-token", {"token":"not-issued-" * 5})]]
[t.start() for t in threads]; [t.join() for t in threads]
a = admin("/runs/v1-public-a-r1"); b = admin("/runs/v1-public-b-r1")
check("15 parallel runs require distinct tokens and charge only the authenticated run",
      first == 200 and responses == {"exhausted-a":429,"valid-b":200,"public-id":403,"legacy-id":403,"unknown-token":403}
      and ra["token"] != rb["token"] and min(len(ra["token"]),len(rb["token"])) >= 32
      and a["spent_usd"] == b["spent_usd"] == 18 and a["calls"] == b["calls"] == 1 and len(calls) == 2,
      f"first={first}, parallel={responses}, calls={len(calls)}, charges A={a['spent_usd']}, B={b['spent_usd']}")
stop(p); p = start(budget=10 ** 9)
restarted = post(body, "v1-public-b-r1")
closed = admin("/runs/v1-public-b-r1/close", {})
revoked = post(body, "v1-public-b-r1")
stop(p)
artifacts = open(SF).read() + open(f"{tmp}/gateway.log").read() + json.dumps(forwarded_headers) + json.dumps([a,b,closed])
check("16 token mapping survives restart, closing revokes it, and bearer tokens are not recorded or forwarded",
      restarted == 200 and revoked == 403 and all(token not in artifacts for token in TOKENS.values())
      and all("token" not in result and "token_hash" not in result for result in (a,b,closed)),
      f"restart={restarted}, closed-token={revoked}, no bearer in artifacts")

# Force the close between the initial lookup and the reservation lock, without adding test hooks to the gateway.
import email.message, hashlib, importlib.util, io
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('gateway_race_fixture', f'{HERE}/gateway.py')
gw = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {'KEY_FILE':f'{tmp}/key','ADMIN_KEY_FILE':f'{tmp}/admin-key',
                            'STATE_FILE':f'{tmp}/race-state.json','PRICES':'{"m":[1,1]}'}):
    spec.loader.exec_module(gw)
digest = hashlib.sha256(b'race-token').hexdigest()
gw.state['runs']['race'] = {'cap_usd':1,'spent_usd':0,'calls':0,'open':True,'token_hash':digest}
gw.token_runs[digest] = 'race'
entered, release = threading.Event(), threading.Event()
def paused_price(*args, **kwargs):
    entered.set()
    if not release.wait(5): raise RuntimeError('test synchronization timeout')
    return 0.01
request = object.__new__(gw.H); request.path='/v1/messages'; request.headers=email.message.Message()
raw=json.dumps(body).encode();request.headers['content-length']=str(len(raw));request.headers['x-run-token']='race-token';request.rfile=io.BytesIO(raw)
status=[];request.refuse=lambda code,why:status.append(code)
admin_request=object.__new__(gw.Admin);admin_request.path='/runs/race/close';admin_request.headers=email.message.Message()
admin_request.headers['Authorization']='Bearer fake-admin';admin_request.headers['content-length']='2';admin_request.rfile=io.BytesIO(b'{}')
admin_status=[];admin_request.reply=lambda code,obj:admin_status.append(code)
with patch.object(gw,'usd',side_effect=paused_price),patch.object(gw.UPSTREAM_HTTP,'open',side_effect=AssertionError('must not forward')) as upstream,patch.object(gw,'log'):
    worker=threading.Thread(target=request.do_POST);worker.start();reached=entered.wait(5)
    if reached:admin_request.do_POST()
    release.set();worker.join(5)
    check("17 closing a run between lookup and reservation prevents forwarding",
          reached and not worker.is_alive() and admin_status==[200] and status==[403] and not upstream.called
          and not gw.state['reserved'] and gw.state['spent_usd']==0,
          f"closed={admin_status}, request={status}, forwarded={upstream.called}")
sys.exit(0 if ok else 1)
