#!/usr/bin/env python3
"""Inference gateway, v4 (experiment 04). Amendment of 12/11 (Francisco): the input estimate is request bytes / 2, not
bytes / 1. In the smoke test the bytes/1 reservation passed the US$0.33 per-attempt cap once a conversation passed about
95 KB, while the real cost per call was about US$0.01, so long attempts would have been stopped by the estimate, not by
spending. The check that halts the gateway when a call costs more than its reservation stays.
Changes from v3 (experiment 03):
  - PER-RUN BUDGETS. Every call must carry x-run-token, a random credential returned when the runner opens a run on
    the ADMIN port (8081), which the agent's NetworkPolicy does not allow it to reach. Public run ids are labels only.
    Token authentication replaced x-run-id after collection on 2026-11-12; only token hashes are persisted.
    A run has its own cap (US$0.33 in this experiment); a call that would pass it is refused (429) before forwarding.
    Unknown or closed run tokens are refused (403). The total cap
    (BUDGET_USD) still applies on top. Reservations carry their run id, so a crash books them to that run.
  - PROMPT CACHING, priced. cache_control {"type": "ephemeral"} (5-minute TTL only) is allowed on text and
    tool_result blocks. Booking prices cache writes at 1.25x and cache reads at the model's read multiplier (0.05x
    Sonnet 5.5, 0.1x Haiku 5.5; pricing page checked 2026-11-11). The reservation assumes every input token is a
    cache write (1.25x), the most expensive case.

Inference gateway: the only thing the agent's pod may talk to. It holds the provider key, forwards exactly one
operation (POST /v1/messages) to exactly one host, enforces a budget, and logs every request. It is not a proxy:
any other method, path or absolute URL is refused with 403.

Request format (v4): only what this agent needs. Top-level fields model, max_tokens, messages, system (a string),
tools (client tools: name, description, input_schema) and tool_choice; message content is text, tool_use and
tool_result blocks, plus the thinking blocks the model itself returned, sent back unchanged in assistant turns (the
model may return them even when thinking was not requested; they are text the gateway holds, like the rest).
Everything else is refused before it is forwarded: images and documents (inline, by URL or by file id), server-side
tools, MCP servers, unsupported cache TTLs, the thinking parameter, streaming, unknown fields. So nothing the provider fetches
or runs on its side can add tokens or fees the gateway did not count.

Budget (v3): a conservative ESTIMATED reservation per call, made durable before the call, and a stop when what the
provider reports exceeds the estimate. It is not a guarantee about money: if a call costs more than its reservation,
that call has already happened; the gateway can only refuse the next ones.
  reservation of one call = (request bytes / 2 + OVERHEAD_TOK) input tokens + max_tokens output tokens, at the price of
    the tier that many input tokens would fall in. Reasoning: for the allowed format the input is text the gateway
    holds, a token covers about two bytes of it or more (bytes / 2 since 12/11, see below), and OVERHEAD_TOK covers what the provider adds around it (tool-use
    preamble, message framing). That is an estimate checked against every response, not a contract with the provider.
  prices: per model, with the provider's long-prompt tier where it has one (Haiku 5.5: a request whose prompt is over
    100,000 tokens, cache reads and writes included, pays the higher prices on the whole request). The reservation
    uses the tier of the estimated input; the booking uses the tier of the prompt length the provider reports.
  1. under a lock: refuse (429) if spent + reserved + this reservation would pass BUDGET_USD;
  2. write the reservation to STATE_FILE and fsync it; if that fails, refuse (503) and forward nothing;
  3. forward; then replace the reservation by the cost of the reported usage and write again.
  At start, reservations found in the file belong to calls that were in flight when the process died: they are booked
  as spent at their reserved amount. A state file that exists but cannot be read, or a state that cannot be written,
  stops the gateway instead of starting from zero. If a response costs more than its reservation, the gateway halts
  (503 from then on) and says so in the log."""
import hashlib, hmac, json, math, os, secrets, sys, threading, time, urllib.request, urllib.error, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "https://api.anthropic.com/v1/messages")
KEY = open(os.environ.get("KEY_FILE", "/secrets/key")).read().strip()
ADMIN_KEY = open(os.environ.get("ADMIN_KEY_FILE", "/admin-secrets/key")).read().strip()
if not ADMIN_KEY: raise ValueError("admin key must not be empty")
# USD per million tokens: [input, output], or [input, output, T, input_long, output_long] when a request whose prompt
# is over T tokens pays the long prices on all of its tokens. Only models listed here are allowed.
# Checked against https://platform.claude.com/docs/en/about-claude/pricing on 2026-11-11.
PRICES = json.loads(os.environ.get("PRICES", '{"claude-sonnet-5-5": [2.0, 10.0], "claude-haiku-5-5": [0.1, 0.5, 100000, 0.5, 2.5]}'))
BUDGET_USD = float(os.environ.get("BUDGET_USD", "5"))
if not math.isfinite(BUDGET_USD) or BUDGET_USD <= 0: raise ValueError("invalid total budget")
MAX_TOKENS_PER_CALL = int(os.environ.get("MAX_TOKENS_PER_CALL", "8192"))
OVERHEAD_TOK = int(os.environ.get("OVERHEAD_TOK", "2000"))
UPSTREAM_TIMEOUT_S = int(os.environ.get("UPSTREAM_TIMEOUT_S", "300"))
STATE_FILE = os.environ.get("STATE_FILE", "/state/budget.json")
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "8081"))
MAX_RUN_USD = float(os.environ.get("MAX_RUN_USD", "0.33"))
if not math.isfinite(MAX_RUN_USD) or MAX_RUN_USD <= 0: raise ValueError("invalid maximum run budget")
WRITE_X = 1.25                                                       # 5-minute cache write
READ_X = {"claude-sonnet-5-5": 0.05, "claude-haiku-5-5": 0.1}         # cache hit, as a fraction of the base input price
HTTP_READ_TIMEOUT_S = float(os.environ.get("HTTP_READ_TIMEOUT_S", "15"))
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "32"))
if MAX_CONNECTIONS <= 0 or not math.isfinite(HTTP_READ_TIMEOUT_S) or HTTP_READ_TIMEOUT_S <= 0:
    raise ValueError("invalid HTTP resource limits")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

UPSTREAM_HTTP = urllib.request.build_opener(NoRedirect)

class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)
    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request, client_address)
        except Exception:
            self.slots.release(); raise
    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()
    def handle_error(self, request, client_address):
        log(event="http_connection_error")  # no headers or credentials in diagnostics

class TimedHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(HTTP_READ_TIMEOUT_S)

lock = threading.Lock()
state = {"spent_usd": 0.0, "requests": 0, "in_tok": 0, "out_tok": 0, "reserved": {}, "halted": None, "runs": {}}
token_runs = {}  # SHA-256 of an unpredictable bearer token -> public run id; never store the bearer itself
# A close that could not be written: the file may still say the run is open, so after a restart load() would accept
# its token again. In this process the run stays closed and the token revoked, and the gateway halts (nothing is
# forwarded) until a close is written; that write carries every closure made in memory. What cannot be fixed here:
# while the state cannot be written, a revocation cannot be made durable, so a restart before that write brings the
# token back. The runner must treat a failed close as fatal (cases/attempt.sh does).
CLOSE_HALT = "a run close could not be written to the state file; close that run again once the state is writable"

def public_run(run): return {k: v for k, v in run.items() if k != "token_hash"}

def log(**kw): print(json.dumps({"ts": round(time.time(), 3), **kw}), flush=True)

def save():
    """Durable write: temp file, fsync, rename, fsync of the directory. Raises OSError if any step fails."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)
    d = os.open(os.path.dirname(STATE_FILE) or ".", os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)

def load():
    if os.path.exists(STATE_FILE):
        state.update(json.load(open(STATE_FILE)))            # unreadable state: stop here, never start from zero
        state.setdefault("reserved", {}); state.setdefault("halted", None); state.setdefault("runs", {})
        if state["reserved"]:                                # calls in flight when the process died: count them in full
            lost = sum(v["usd"] for v in state["reserved"].values())
            log(event="recovered_reservations", calls=len(state["reserved"]), usd=round(lost, 6))
            for v in state["reserved"].values():
                r = state["runs"].get(v["run"])
                if r: r["spent_usd"] += v["usd"]
            state["spent_usd"] += lost; state["requests"] += len(state["reserved"]); state["reserved"] = {}
    token_runs.clear()
    token_runs.update((r["token_hash"], run) for run, r in state["runs"].items() if r.get("open") and r.get("token_hash"))
    save()                                                   # the state must be writable before the first call

def usd(model, prompt_tok, tout, cache_write=0, cache_read=0):
    """Cost of one call. prompt_tok = ALL input tokens, cache reads and writes included (it also picks the price tier);
    of those, cache_write are billed at WRITE_X and cache_read at the model's READ_X, the rest at the base price."""
    p = PRICES[model]; pi, po = p[0], p[1]
    if len(p) >= 5 and prompt_tok > p[2]: pi, po = p[3], p[4]
    plain = prompt_tok - cache_write - cache_read
    return ((plain + WRITE_X * cache_write + READ_X.get(model, 1.0) * cache_read) * pi + tout * po) / 1e6

def reserved_total(): return sum(v["usd"] for v in state["reserved"].values())
def reserved_run(run): return sum(v["usd"] for v in state["reserved"].values() if v["run"] == run)

TOP = {"model", "max_tokens", "messages", "system", "tools", "tool_choice"}
def only(d, keys, nullable=()):
    """d is a dict whose keys are all in `keys`, or in `nullable` with a null value."""
    return isinstance(d, dict) and all(k in keys or (k in nullable and v is None) for k, v in d.items())
def cache_ok(b): return "cache_control" not in b or b["cache_control"] in ({"type": "ephemeral"}, {"type": "ephemeral", "ttl": "5m"})
def text_block(b): return only(b, {"type", "text", "cache_control"}, {"citations"}) and b.get("type") == "text" and isinstance(b.get("text"), str) and cache_ok(b)
def block_ok(b, role):
    t = b.get("type") if isinstance(b, dict) else None
    if t == "text": return text_block(b)
    if t == "thinking" and role == "assistant": return only(b, {"type", "thinking", "signature"})
    if t == "redacted_thinking" and role == "assistant": return only(b, {"type", "data"})
    if t == "tool_use": return only(b, {"type", "id", "name", "input"}, {"caller"}) or (only(b, {"type", "id", "name", "input", "caller"}) and b["caller"] == {"type": "direct"})
    if t == "tool_result":
        c = b.get("content", "")
        return only(b, {"type", "tool_use_id", "content", "is_error", "cache_control"}) and cache_ok(b) and (isinstance(c, str) or (isinstance(c, list) and all(text_block(x) for x in c)))
    return False
def format_error(body):
    """None if the request uses only the allowed format, else why not."""
    if not isinstance(body, dict): return "body is not an object"
    extra = sorted(set(body) - TOP)
    if extra: return "field not allowed: " + ", ".join(extra)[:80]
    if not isinstance(body.get("system", ""), str): return "system must be a plain string"
    for t in body.get("tools", []) if isinstance(body.get("tools", []), list) else [None]:
        if not (only(t, {"name", "description", "input_schema"}) and isinstance(t.get("input_schema"), dict)): return "only client tools (name, description, input_schema) are allowed"
    if "tool_choice" in body and not only(body["tool_choice"], {"type", "name", "disable_parallel_tool_use"}): return "tool_choice not allowed in this form"
    if not isinstance(body.get("messages"), list): return "messages must be a list"
    for m in body["messages"]:
        if not (only(m, {"role", "content"}) and m.get("role") in ("user", "assistant")): return "message not allowed in this form"
        c = m.get("content")
        if isinstance(c, str): continue
        if not isinstance(c, list): return "message content must be text or a list of blocks"
        for b in c:
            if not block_ok(b, m["role"]): return "content block not allowed: " + str(b.get("type") if isinstance(b, dict) else type(b).__name__)[:40]
    return None

class H(TimedHandler):
    protocol_version = "HTTP/1.1"
    def refuse(self, code, why):
        log(src=self.client_address[0], method=self.command, path=self.path[:200], verdict="refused", why=why, status=code,
            run=getattr(self, "run", None))
        out = json.dumps({"error": why}).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out))); self.send_header("connection", "close"); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200); self.send_header("content-length", "3"); self.end_headers(); self.wfile.write(b"ok\n"); return
        self.refuse(403, "only POST /v1/messages is allowed")
    def do_CONNECT(self): self.refuse(403, "not a proxy")
    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = lambda self: self.refuse(403, "only POST /v1/messages is allowed")
    def do_POST(self):
        self.run = None
        if self.path != "/v1/messages":            # also catches absolute URLs sent by clients that treat us as a proxy
            return self.refuse(403, "only POST /v1/messages is allowed")
        try: n = int(self.headers.get("content-length") or 0)
        except ValueError: return self.refuse(400, "bad body size")
        if n <= 0 or n > 4_000_000: return self.refuse(413, "bad body size")
        raw = self.rfile.read(n)
        try: body = json.loads(raw)
        except Exception: return self.refuse(400, "body is not JSON")
        why = format_error(body)
        if why: return self.refuse(403, why)
        model = body.get("model")
        if model not in PRICES: return self.refuse(403, "model not allowed")
        token_hash = hashlib.sha256(self.headers.get("x-run-token", "").encode()).hexdigest()
        with lock:
            run = token_runs.get(token_hash)
            r = state["runs"].get(run)
        if not r or not r.get("open"): return self.refuse(403, "unknown or closed run token")
        self.run = run
        try: body["max_tokens"] = max(1, min(int(body.get("max_tokens") or 1024), MAX_TOKENS_PER_CALL))
        except (TypeError, ValueError, OverflowError): return self.refuse(400, "max_tokens is not a number")
        payload = json.dumps(body).encode()
        bound_in = (len(payload) + 1) // 2 + OVERHEAD_TOK          # bytes / 2 (amendment of 12/11, criteria.md)
        bound = usd(model, bound_in, body["max_tokens"], cache_write=bound_in)   # estimate: every input token a cache write
        rid, no = uuid.uuid4().hex[:12], None
        with lock:
            if not r.get("open"): no = (403, "run was closed before reservation")
            elif state["halted"]: no = (503, "gateway halted: " + state["halted"])
            elif state["spent_usd"] + reserved_total() + bound > BUDGET_USD:
                left = BUDGET_USD - state["spent_usd"] - reserved_total()
                no = (429, f"gateway budget: this call reserves ${bound:.4f}, ${max(left, 0):.4f} left")
            elif r["spent_usd"] + reserved_run(run) + bound > r["cap_usd"]:
                left = r["cap_usd"] - r["spent_usd"] - reserved_run(run)
                no = (429, f"run budget: this call reserves ${bound:.4f}, ${max(left, 0):.4f} left in run {run}")
            else:
                state["reserved"][rid] = {"usd": bound, "run": run}
                try: save()                                             # durable BEFORE forwarding, or nothing is forwarded
                except OSError as e:
                    del state["reserved"][rid]; no = (503, f"cannot persist the budget reservation ({type(e).__name__}); not forwarding")
        if no: return self.refuse(*no)
        hdr = {"content-type": "application/json", "x-api-key": KEY,
               "anthropic-version": self.headers.get("anthropic-version", "2023-06-01")}
        t0 = time.time(); status, out, err = None, b"", None
        try:
            with UPSTREAM_HTTP.open(urllib.request.Request(UPSTREAM, data=payload, headers=hdr, method="POST"), timeout=UPSTREAM_TIMEOUT_S) as resp:
                status, out = resp.status, resp.read()
        except urllib.error.HTTPError as e: status, out = e.code, e.read()
        except Exception as e: err = type(e).__name__
        u = {}
        try: u = json.loads(out).get("usage", {}) or {}
        except Exception: pass
        cw, cr = u.get("cache_creation_input_tokens", 0) or 0, u.get("cache_read_input_tokens", 0) or 0
        tin = (u.get("input_tokens", 0) or 0) + cr + cw
        tout = u.get("output_tokens", 0) or 0
        # no usage in the response (timeout, broken body): keep the bound on the books rather than assume it was free
        real = usd(model, tin, tout, cache_write=cw, cache_read=cr) if u else (bound if (err or status == 200) else 0.0)
        over = real > bound + 1e-12 or bool(u.get("server_tool_use"))
        with lock:
            state["reserved"].pop(rid, None)
            state["spent_usd"] += real; state["requests"] += 1; state["in_tok"] += tin; state["out_tok"] += tout
            if run in state["runs"]: state["runs"][run]["spent_usd"] += real; state["runs"][run]["calls"] = state["runs"][run].get("calls", 0) + 1
            if over: state["halted"] = f"a call cost ${real:.6f}, above its reservation ${bound:.6f}"
            try: save()
            except OSError as e: log(event="state_write_failed", why=type(e).__name__)    # the file still holds the reservation
            spent = state["spent_usd"]
        if over: log(event="bound_exceeded", run=run, usd=round(real, 6), bound_usd=round(bound, 6), in_tok=tin, bound_in_tok=bound_in)
        if err: return self.refuse(502, f"upstream error: {err}")
        log(src=self.client_address[0], method="POST", path="/v1/messages", verdict="forwarded", status=status, model=model,
            run=run, in_tok=tin, cache_write=cw, cache_read=cr, bound_in_tok=bound_in, out_tok=tout, usd=round(real, 6), bound_usd=round(bound, 6),
            spent_usd=round(spent, 6), ms=int((time.time() - t0) * 1000))
        self.send_response(status); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass

class Admin(TimedHandler):
    """Runner-only port (the agent's NetworkPolicy allows 8080 only). POST /runs {"run": id, "cap_usd": x} opens a run;
    Only opening returns the random model token. POST /runs/<id>/close revokes it; GET /runs/<id> reports the run
    without its credential; GET /state reports the totals. A close that cannot be written answers 503, keeps the run
    closed in memory and halts the gateway until a close is written (CLOSE_HALT)."""
    protocol_version = "HTTP/1.1"
    def reply(self, code, obj):
        out = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def authenticated(self):
        if hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + ADMIN_KEY).encode()): return True
        self.close_connection = True
        self.reply(401, {"error": "admin authentication required"})
        return False
    def do_GET(self):
        if not self.authenticated(): return
        with lock:
            if self.path == "/state": return self.reply(200, {k: state[k] for k in ("spent_usd", "requests", "in_tok", "out_tok", "halted")} | {"reserved_usd": reserved_total(), "budget_usd": BUDGET_USD})
            r = state["runs"].get(self.path.rsplit("/", 1)[-1])
        return self.reply(200, public_run(r)) if r else self.reply(404, {"error": "no such run"})
    def do_POST(self):
        if not self.authenticated(): return
        try:
            n = int(self.headers.get("content-length") or 0)
            if not 0 < n <= 16384: return self.reply(400, {"error": "bad body size"})
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict): return self.reply(400, {"error": "body must be an object"})
        except (ValueError, UnicodeError): return self.reply(400, {"error": "invalid JSON body"})
        token = None
        with lock:
            halted_before = state["halted"]
            if self.path == "/runs":
                run = str(body.get("run", ""))
                try: cap = float(body.get("cap_usd", 0))
                except (TypeError, ValueError, OverflowError): return self.reply(400, {"error": "invalid run cap"})
                if not math.isfinite(cap) or not 0 < cap <= MAX_RUN_USD:
                    return self.reply(400, {"error": "run cap must be finite, positive and within MAX_RUN_USD"})
                if not run or run in state["runs"]: return self.reply(409, {"error": "missing or reused run id"})
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                state["runs"][run] = {"cap_usd": cap, "spent_usd": 0.0, "calls": 0, "open": True, "opened": time.time(), "token_hash": token_hash}
            elif self.path.startswith("/runs/") and self.path.endswith("/close"):
                run = self.path.split("/")[2]
                if run not in state["runs"]: return self.reply(404, {"error": "no such run"})
                state["runs"][run]["open"] = False; state["runs"][run]["closed"] = time.time()
                token_runs.pop(state["runs"][run].get("token_hash"), None)
                if halted_before == CLOSE_HALT: state["halted"] = None   # if the save below succeeds, every closure is on disk
            else: return self.reply(404, {"error": "no such endpoint"})
            try: save()
            except OSError as e:
                if token is not None: del state["runs"][run]
                else:                                   # see CLOSE_HALT: stay closed in memory, forward nothing
                    state["halted"] = halted_before or CLOSE_HALT
                    log(event="close_not_persisted", run=run, why=type(e).__name__)
                return self.reply(503, {"error": f"cannot persist ({type(e).__name__})"})
            if token is not None: token_runs[token_hash] = run
            out = public_run(state["runs"][run])
        log(event="run_" + ("opened" if self.path == "/runs" else "closed"), run=run, cap_usd=out["cap_usd"], spent_usd=round(out["spent_usd"], 6), calls=out.get("calls", 0))
        return self.reply(200, out | ({"token": token} if token is not None else {}))
    def log_message(self, *a): pass

if __name__ == "__main__":
    try: load()
    except Exception as e:
        log(event="refusing_to_start", why=f"budget state unusable: {type(e).__name__}: {str(e)[:120]}"); sys.exit(1)
    log(event="start", models=sorted(PRICES), budget_usd=BUDGET_USD, spent_usd=round(state["spent_usd"], 6), halted=state["halted"])
    threading.Thread(target=BoundedHTTPServer(("0.0.0.0", ADMIN_PORT), Admin).serve_forever, daemon=True).start()
    BoundedHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), H).serve_forever()
