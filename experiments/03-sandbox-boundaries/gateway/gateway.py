#!/usr/bin/env python3
"""Inference gateway: the only thing the agent's pod may talk to. It holds the provider key, forwards exactly one
operation (POST /v1/messages) to exactly one host, enforces a budget, and logs every request. It is not a proxy:
any other method, path or absolute URL is refused with 403.

Request format (v3): only what this agent needs. Top-level fields model, max_tokens, messages, system (a string),
tools (client tools: name, description, input_schema) and tool_choice; message content is text, tool_use and
tool_result blocks, plus the thinking blocks the model itself returned, sent back unchanged in assistant turns (the
model may return them even when thinking was not requested; they are text the gateway holds, like the rest).
Everything else is refused before it is forwarded: images and documents (inline, by URL or by file id), server-side
tools, MCP servers, cache_control, the thinking parameter, streaming, unknown fields. So nothing the provider fetches
or runs on its side can add tokens or fees the gateway did not count.

Budget (v3): a conservative ESTIMATED reservation per call, made durable before the call, and a stop when what the
provider reports exceeds the estimate. It is not a guarantee about money: if a call costs more than its reservation,
that call has already happened; the gateway can only refuse the next ones.
  reservation of one call = (request bytes + OVERHEAD_TOK) input tokens + max_tokens output tokens, at the price of
    the tier that many input tokens would fall in. Reasoning: for the allowed format the input is text the gateway
    holds, a token covers at least one byte of it, and OVERHEAD_TOK covers what the provider adds around it (tool-use
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
import json, os, sys, threading, time, urllib.request, urllib.error, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "https://api.anthropic.com/v1/messages")
KEY = open(os.environ.get("KEY_FILE", "/secrets/key")).read().strip()
# USD per million tokens: [input, output], or [input, output, T, input_long, output_long] when a request whose prompt
# is over T tokens pays the long prices on all of its tokens. Only models listed here are allowed.
# Checked against https://platform.claude.com/docs/en/about-claude/pricing on 2026-11-11.
PRICES = json.loads(os.environ.get("PRICES", '{"claude-sonnet-5-5": [2.0, 10.0], "claude-haiku-5-5": [0.1, 0.5, 100000, 0.5, 2.5]}'))
BUDGET_USD = float(os.environ.get("BUDGET_USD", "5"))
MAX_TOKENS_PER_CALL = int(os.environ.get("MAX_TOKENS_PER_CALL", "8192"))
OVERHEAD_TOK = int(os.environ.get("OVERHEAD_TOK", "2000"))
CACHE_WRITE_X = 2.0     # if the provider ever reports cache writes (the format forbids asking for them), bill them high
UPSTREAM_TIMEOUT_S = int(os.environ.get("UPSTREAM_TIMEOUT_S", "300"))
STATE_FILE = os.environ.get("STATE_FILE", "/state/budget.json")
lock = threading.Lock()
state = {"spent_usd": 0.0, "requests": 0, "in_tok": 0, "out_tok": 0, "reserved": {}, "halted": None}

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
        state.setdefault("reserved", {}); state.setdefault("halted", None)
        if state["reserved"]:                                # calls in flight when the process died: count them in full
            lost = sum(state["reserved"].values())
            log(event="recovered_reservations", calls=len(state["reserved"]), usd=round(lost, 6))
            state["spent_usd"] += lost; state["requests"] += len(state["reserved"]); state["reserved"] = {}
    save()                                                   # the state must be writable before the first call

def usd(model, prompt_tok, tout, extra_in=0.0):
    """Cost of one call. prompt_tok = all input tokens (it also picks the price tier); extra_in = input-token
    equivalents billed on top (the surcharge of cache writes)."""
    p = PRICES[model]; pi, po = p[0], p[1]
    if len(p) >= 5 and prompt_tok > p[2]: pi, po = p[3], p[4]
    return ((prompt_tok + extra_in) * pi + tout * po) / 1e6

TOP = {"model", "max_tokens", "messages", "system", "tools", "tool_choice"}
def only(d, keys, nullable=()):
    """d is a dict whose keys are all in `keys`, or in `nullable` with a null value."""
    return isinstance(d, dict) and all(k in keys or (k in nullable and v is None) for k, v in d.items())
def text_block(b): return only(b, {"type", "text"}, {"citations"}) and b.get("type") == "text" and isinstance(b.get("text"), str)
def block_ok(b, role):
    t = b.get("type") if isinstance(b, dict) else None
    if t == "text": return text_block(b)
    if t == "thinking" and role == "assistant": return only(b, {"type", "thinking", "signature"})
    if t == "redacted_thinking" and role == "assistant": return only(b, {"type", "data"})
    if t == "tool_use": return only(b, {"type", "id", "name", "input"}, {"caller"}) or (only(b, {"type", "id", "name", "input", "caller"}) and b["caller"] == {"type": "direct"})
    if t == "tool_result":
        c = b.get("content", "")
        return only(b, {"type", "tool_use_id", "content", "is_error"}) and (isinstance(c, str) or (isinstance(c, list) and all(text_block(x) for x in c)))
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

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def refuse(self, code, why):
        log(src=self.client_address[0], method=self.command, path=self.path[:200], verdict="refused", why=why, status=code,
            run=self.headers.get("x-run-id", ""))
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
        if self.path != "/v1/messages":            # also catches absolute URLs sent by clients that treat us as a proxy
            return self.refuse(403, "only POST /v1/messages is allowed")
        n = int(self.headers.get("content-length") or 0)
        if n <= 0 or n > 4_000_000: return self.refuse(413, "bad body size")
        raw = self.rfile.read(n)
        try: body = json.loads(raw)
        except Exception: return self.refuse(400, "body is not JSON")
        why = format_error(body)
        if why: return self.refuse(403, why)
        model = body.get("model")
        if model not in PRICES: return self.refuse(403, "model not allowed")
        try: body["max_tokens"] = max(1, min(int(body.get("max_tokens") or 1024), MAX_TOKENS_PER_CALL))
        except (TypeError, ValueError): return self.refuse(400, "max_tokens is not a number")
        payload = json.dumps(body).encode()
        bound_in = len(payload) + OVERHEAD_TOK
        bound = usd(model, bound_in, body["max_tokens"])               # the estimated reservation, at the tier bound_in falls in
        rid, no = uuid.uuid4().hex[:12], None
        with lock:
            if state["halted"]: no = (503, "gateway halted: " + state["halted"])
            elif state["spent_usd"] + sum(state["reserved"].values()) + bound > BUDGET_USD:
                left = BUDGET_USD - state["spent_usd"] - sum(state["reserved"].values())
                no = (429, f"gateway budget: this call reserves ${bound:.4f}, ${max(left, 0):.4f} left")
            else:
                state["reserved"][rid] = bound
                try: save()                                             # durable BEFORE forwarding, or nothing is forwarded
                except OSError as e:
                    del state["reserved"][rid]; no = (503, f"cannot persist the budget reservation ({type(e).__name__}); not forwarding")
        if no: return self.refuse(*no)
        hdr = {"content-type": "application/json", "x-api-key": KEY,
               "anthropic-version": self.headers.get("anthropic-version", "2023-06-01")}
        t0 = time.time(); status, out, err = None, b"", None
        try:
            with urllib.request.urlopen(urllib.request.Request(UPSTREAM, data=payload, headers=hdr, method="POST"), timeout=UPSTREAM_TIMEOUT_S) as resp:
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
        real = usd(model, tin, tout, extra_in=(CACHE_WRITE_X - 1) * cw) if u else (bound if (err or status == 200) else 0.0)
        over = real > bound + 1e-12 or bool(u.get("server_tool_use"))
        with lock:
            state["reserved"].pop(rid, None)
            state["spent_usd"] += real; state["requests"] += 1; state["in_tok"] += tin; state["out_tok"] += tout
            if over: state["halted"] = f"a call cost ${real:.6f}, above its reservation ${bound:.6f}"
            try: save()
            except OSError as e: log(event="state_write_failed", why=type(e).__name__)    # the file still holds the reservation
            spent = state["spent_usd"]
        if over: log(event="bound_exceeded", run=self.headers.get("x-run-id", ""), usd=round(real, 6), bound_usd=round(bound, 6), in_tok=tin, bound_in_tok=bound_in)
        if err: return self.refuse(502, f"upstream error: {err}")
        log(src=self.client_address[0], method="POST", path="/v1/messages", verdict="forwarded", status=status, model=model,
            run=self.headers.get("x-run-id", ""), in_tok=tin, bound_in_tok=bound_in, out_tok=tout, usd=round(real, 6), bound_usd=round(bound, 6),
            spent_usd=round(spent, 6), ms=int((time.time() - t0) * 1000))
        self.send_response(status); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass

if __name__ == "__main__":
    try: load()
    except Exception as e:
        log(event="refusing_to_start", why=f"budget state unusable: {type(e).__name__}: {str(e)[:120]}"); sys.exit(1)
    log(event="start", models=sorted(PRICES), budget_usd=BUDGET_USD, spent_usd=round(state["spent_usd"], 6), halted=state["halted"])
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), H).serve_forever()
