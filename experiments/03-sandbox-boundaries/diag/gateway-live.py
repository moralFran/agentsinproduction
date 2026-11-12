"""Runs INSIDE a pod made from the agent's image and spec (passed to python3 -c by diag/run-gateway-live.sh): the gateway's
handling of untrusted clients, seen from the agent's position, in the cluster. One JSON line per check.
One real model call (Haiku, 8 output tokens) is made, in the version-header check; everything else is refused or cut
by the gateway before anything is forwarded. The same behaviour is tested offline in gateway/test_budget.py (9-12)."""
import json, socket, time
GW = ("10.43.200.10", 8080)
REQ = "POST /v1/messages HTTP/1.1\r\nHost: gateway\r\nContent-Type: application/json\r\nx-run-id: gateway-live\r\n"
CALL = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 8, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]})
def raw(data, wait):
    """-> (status line, or "closed" / "no answer", seconds)."""
    t = time.time(); buf = b""; state = "no answer"
    try:
        s = socket.create_connection(GW, timeout=5); s.sendall(data); s.settimeout(1)
        while time.time() - t < wait:
            try:
                c = s.recv(65536)
                if not c: state = "closed"; break
                buf += c
            except socket.timeout: pass
            except OSError: state = "closed"; break
        s.close()
    except OSError as e: state = f"connect failed: {e}"
    return (buf.split(b"\r\n", 1)[0].decode(errors="replace") if buf else state), round(time.time() - t, 1)
def report(check, expected, got, seconds, ok): print(json.dumps({"check": check, "expected": expected, "got": got, "seconds": seconds, "ok": ok}), flush=True)

got, s = raw((REQ + "Content-Length: abc\r\n\r\n" + CALL).encode(), 10)
report("Content-Length that is not a number", "400", got, s, " 400 " in got)
body = json.dumps({"model": ["claude-haiku-5-5"], "max_tokens": 8, "messages": []})
got, s = raw((REQ + f"Content-Length: {len(body)}\r\n\r\n" + body).encode(), 10)
report("model that is a list", "400", got, s, " 400 " in got)
got, s = raw((REQ + "Content-Length: 1000\r\n\r\n" + CALL[:10]).encode(), 40)
report("body that never completes (10 of 1,000 bytes)", "408 at the gateway's read deadline (15 s unless configured)", got, s, " 408 " in got and 10 <= s <= 25)
got, s = raw(REQ.encode(), 40)
report("headers that never complete", "cut at the read deadline: closed, or 400 for the headers that did arrive", got, s, (got == "closed" or " 400 " in got) and 10 <= s <= 25)
idle = []
try:
    for _ in range(8): idle.append(socket.create_connection(GW, timeout=5))
    time.sleep(0.5); got, s = raw(b"", 5)
finally:
    for c in idle: c.close()
report("a 9th connection while 8 from this pod are open and idle", "503 at once (the limit per source address is 8)", got, s, " 503 " in got and s < 3)
time.sleep(1)
hdr = "anthropic-version: 1999-01-01\r\nx-api-key: from-the-client\r\n"
got, s = raw((REQ + hdr + f"Content-Length: {len(CALL)}\r\n\r\n" + CALL).encode(), 60)
report("a valid call that sends anthropic-version 1999-01-01 and its own key", "200: the gateway sends its own version and key (the provider refuses an unknown version)", got, s, " 200 " in got)
