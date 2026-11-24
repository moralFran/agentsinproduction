#!/usr/bin/env python3
"""Cache-break reproductions of experiment 06 (V7, A-v08; protocol of 12/11/2026 with the amendment of 23/11: K = 20,
one reproduction per condition). Runs ON aip-ctx-01, outside any pod, against the gateway (v5).

The trajectory is the first K successful requests of one recorded live attempt (the gateway's request log of the smoke
L0 attempt). Request k of a reproduction is request k as recorded (same system, tools and history, with the model's
recorded answers), with ONE transformation; the new answer is never used (max_tokens 0: the API only reads/writes the
cache and bills no output). So the only difference between two reproductions is their transformation.

  R0      control: none
  R1      a line "Current time: <hh:mm:ss>" at the end of the system prompt, new at every request
  R2      the tool list in reversed order on every even request (the 2 tools alternate)
  R3      output_config {"effort": "medium"} from request MID on (the model's default is high): one change, kept
  R4      the harness sleeps 6 min before requests Q1, MID and Q3 (simulated pauses; nobody paused)
  R4-1h   R4 with every cache_control at ttl "1h"
  R5      from request MID on, the reminder of request 5 is deleted from the history (an edit of earlier history)
  R5-sys  from request MID on, the reminder stays and a {"role": "system"} message with the instruction follows the user
          message of request MID (the append-only way to change instructions)
  R5-drop R5 with thinking.block_binding drop_block: only for an account where R5 is refused (a 400), to still measure it
With K = 20: Q1 = 6, MID = 11, Q3 = 16 (the 11 / 21 / 31 of K = 40 in the protocol).

Isolation: the system prompt starts with "Attempt <id>."; each reproduction replaces it with its own id, so it never
reads the cache written by the live attempt or by another reproduction. Requests run one after another.

Writes one JSON line per request to --out, and the run's booking from the gateway at the end.
usage: replay.py <bodies.jsonl> <condition> [--k 20] [--out results/replays.jsonl] [--cap 3] [--dry]"""
import argparse, copy, json, os, re, subprocess, sys, time, urllib.error, urllib.request

REMINDER = "Reminder: run the commit's tests before you call end_phase."
NEW_INSTRUCTION = "Run the commit's tests before you call end_phase."
DROP_BLOCK = {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
CONDITIONS = ["R0", "R1", "R2", "R3", "R4", "R4-1h", "R5", "R5-sys", "R5-drop"]
FEATURES = {"R3": ["effort"], "R4-1h": ["ttl1h"], "R5-sys": ["system_msg"], "R5-drop": ["drop_block"]}
PAUSE_S = 360
PRICE = {"in": 2.0, "out": 10.0, "w5": 2.5, "w1h": 4.0, "r": 0.10}       # Sonnet 5.5, US$ per million tokens (12/11)

def points(k):
    return k // 4 + 1, k // 2 + 1, 3 * k // 4 + 1                         # K = 20 -> 6, 11, 16

def load(path, k):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    ok = [r["body"] for r in sorted(rows, key=lambda r: r["n"]) if r.get("status") == 200]
    if len(ok) < k: sys.exit(f"the trajectory has {len(ok)} successful requests, fewer than K = {k}")
    return ok[:k]

def reminder_pos(body):
    """(message index, block index) of the reminder in a request's history, or None."""
    for i, m in enumerate(body["messages"]):
        if m["role"] == "user" and isinstance(m["content"], list):
            for j, b in enumerate(m["content"]):
                if b.get("type") == "text" and b.get("text") == REMINDER: return i, j
    return None

def transform(cond, k, body, rid, traj, now=None):
    """Request k (1-based) of reproduction `cond` built from the recorded body. Pure: no I/O, no sleep."""
    q1, mid, q3 = points(len(traj))
    b = copy.deepcopy(body)
    b["max_tokens"] = 0
    if not re.match(r"^Attempt [^\n]*\.", b["system"]): raise ValueError("the recorded system prompt does not start with the attempt id")
    b["system"] = re.sub(r"^Attempt [^\n]*\.", f"Attempt {rid}.", b["system"], count=1)
    if cond == "R1":
        b["system"] += "\n\nCurrent time: " + (now or time.strftime("%H:%M:%S", time.gmtime()))
    elif cond == "R2" and k % 2 == 0:
        b["tools"] = list(reversed(b["tools"]))
    elif cond == "R3" and k >= mid:
        b["output_config"] = {"effort": "medium"}
    elif cond == "R4-1h":
        for m in b["messages"]:
            for blk in (m["content"] if isinstance(m["content"], list) else []):
                if "cache_control" in blk: blk["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    elif cond in ("R5", "R5-drop") and k >= mid:
        pos = reminder_pos(b)
        if pos is None: raise ValueError(f"request {k} has no reminder to delete")
        del b["messages"][pos[0]]["content"][pos[1]]
        if cond == "R5-drop": b["thinking"] = DROP_BLOCK
    elif cond == "R5-sys" and k >= mid:
        at = len(traj[mid - 1]["messages"])          # right after the last message (a user turn) of request MID
        if b["messages"][at - 1]["role"] != "user": raise ValueError("request MID does not end with a user turn")
        b["messages"].insert(at, {"role": "system", "content": NEW_INSTRUCTION})
    return b

def sleeps_before(cond, k, n):
    return PAUSE_S if cond in ("R4", "R4-1h") and k in points(n) else 0

def usd(u):
    cw = u.get("cache_creation_input_tokens", 0) or 0
    w1h = ((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) or 0)
    return ((u.get("input_tokens", 0) or 0) * PRICE["in"] + (cw - w1h) * PRICE["w5"] + w1h * PRICE["w1h"]
            + (u.get("cache_read_input_tokens", 0) or 0) * PRICE["r"] + (u.get("output_tokens", 0) or 0) * PRICE["out"]) / 1e6

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bodies"); ap.add_argument("cond", choices=CONDITIONS)
    ap.add_argument("--k", type=int, default=20); ap.add_argument("--out", default="results/replays.jsonl")
    ap.add_argument("--cap", type=float, default=3.0); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--gateway", default="http://10.43.210.10:8080"); ap.add_argument("--admin", default="http://10.43.210.10:8081")
    a = ap.parse_args()
    traj = load(a.bodies, a.k)
    rid = f"rep-{a.cond}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
    reqs = [transform(a.cond, k, traj[k - 1], rid, traj) for k in range(1, a.k + 1)]     # every request checked before any is sent
    if a.dry:
        for k, b in enumerate(reqs, 1):
            print(k, a.cond, "msgs", len(b["messages"]), "tools", [t["name"] for t in b["tools"]], "effort", (b.get("output_config") or {}).get("effort"),
                  "sys_msgs", sum(m["role"] == "system" for m in b["messages"]), "reminder", reminder_pos(b) is not None, "sleep", sleeps_before(a.cond, k, a.k))
        return
    key = open(os.environ.get("ADMIN_KEY_FILE", "/srv/ci/admin-key")).read().strip()
    def admin(path, body):
        req = urllib.request.Request(a.admin + path, data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    opened = admin("/runs", {"run": rid, "cap_usd": a.cap, "features": ["max_tokens0"] + FEATURES.get(a.cond, [])})
    token = opened.pop("token")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        for k, b in enumerate(reqs, 1):
            pause = sleeps_before(a.cond, k, a.k)
            if pause: time.sleep(pause)
            if a.cond == "R1": b = transform(a.cond, k, traj[k - 1], rid, traj)          # the time line is the time it is sent
            t0 = time.time()
            req = urllib.request.Request(a.gateway + "/v1/messages", data=json.dumps(b).encode(), headers={"x-run-token": token, "content-type": "application/json", "anthropic-version": "2023-06-01"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r: status, out = r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                status = e.code
                try: out = json.loads(e.read())
                except Exception: out = {}
            u = out.get("usage") or {}
            row = {"run": rid, "cond": a.cond, "k": k, "status": status, "slept_s": pause, "ms": int((time.time() - t0) * 1000),
                   "in": u.get("input_tokens"), "cw": u.get("cache_creation_input_tokens"), "cw1h": (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens"),
                   "cr": u.get("cache_read_input_tokens"), "out": u.get("output_tokens"), "usd": round(usd(u), 6) if u else None,
                   "input_transformations": out.get("input_transformations"), "error": str((out.get("error") or {}).get("message", out.get("error", "")))[:400] if status != 200 else ""}
            with open(a.out, "a") as fh: fh.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
    finally:
        closed = admin(f"/runs/{rid}/close", {})
        with open(a.out, "a") as fh: fh.write(json.dumps({"run": rid, "cond": a.cond, "closed": closed}) + "\n")
        print("CLOSED", json.dumps(closed), flush=True)

if __name__ == "__main__":
    main()
