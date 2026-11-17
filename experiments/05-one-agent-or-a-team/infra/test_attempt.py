#!/usr/bin/env python3
"""Offline test of cases/attempt_team.sh against the real gateway and a fake provider (added 2026-11-16, criteria.md
E20). No pod, no provider call, no key: cases/pod.py and cases/validate.py are replaced by stubs in a temporary copy
of the folder. The pod stub makes ONE model call with the run's token and reports what the agent would: `finished`
with a patch on 200; `error` WITH a patch on a 400 (agent.py keeps the working copy on an error, which is how a try cut
by the provider reached the validator on 16/11); `gateway_unavailable` without a patch on 503.
  1. a normal attempt is journaled with the validator's verdict;
  2. the provider refuses the account (400, credit balance) during a run: nothing is journaled although the stub
     validator would say `resolved`; the try goes to the infra file with the gateway's reason; the gateway is halted;
  3. while the gateway is halted, an attempt is not started: no run opened, no infrastructure try used;
  4. after POST /resume the same attempt is redone under a new run id (-t2) and journaled;
  5. cases/void_tries.py on a copy of the round of 16/11 (16 journal lines, 10 of them tries cut by the provider, 4 runs
     of repetition 2 opened and never journaled, two budget records written from the wrong picture): 6 lines stay, the
     10 are kept in the voided file, 14 infra records make the runner use new run ids, the budget gate resumes
     repetition 1 with 10 attempts missing, a second run changes nothing, an unknown run id changes nothing.
Run: python3 infra/test_attempt.py"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP, GW, AD = 18181, 18180, 18182
MODE = {"v": "ok"}

class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["content-length"]))
        if MODE["v"] == "nocredit":
            code, obj = 400, {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}
        else:
            code, obj = 200, {"usage": {"input_tokens": 10, "output_tokens": 8}}
        out = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass

POD_STUB = r'''
import json, os, urllib.request, urllib.error
req = urllib.request.Request(os.environ["STUB_GW"] + "/v1/messages", data=json.dumps({"model": "m", "max_tokens": 8, "messages": []}).encode(),
                             headers={"x-run-token": os.environ["RUN_TOKEN"]})
try: status = urllib.request.urlopen(req, timeout=10).status
except urllib.error.HTTPError as e: status = e.code
res = {200: {"outcome": "finished", "patch": "a patch\n"}, 400: {"outcome": "error", "error": "BadRequestError: Error code: 400", "patch": "a partial patch\n"}}.get(
    status, {"outcome": "gateway_unavailable", "error": f"status {status}", "patch": ""})
print("POD " + json.dumps({"phase": "Succeeded"})); print("RESULT " + json.dumps(res | {"model_calls": 1, "tool_calls": 0, "total_s": 0.1}))
'''

def void_check(check):
    import csv
    tmp = tempfile.mkdtemp(prefix="void-test-"); os.makedirs(f"{tmp}/cases"); os.makedirs(f"{tmp}/results/patches/c1")
    for f in ("cases/void_tries.py", "cases/budget_gate.py", "order.csv"): shutil.copy(f"{ROOT}/{f}", f"{tmp}/{f}")
    rep1 = [r for r in csv.DictReader(l for l in open(f"{ROOT}/order.csv") if not l.startswith("#")) if r["rep"] == "1"]
    hit = ["T4-B", "T7-B", "T1-A", "T1-B", "T2-A", "T2-B", "T3-A", "T5-B", "T6-B", "T7-A"]; opened = ["c1-t5-b-r2", "c1-t7-b-r2", "c1-t1-a-r2", "c1-t2-a-r2"]
    with open(f"{tmp}/results/attempts-c1.jsonl", "w") as f:
        for r in rep1:
            run = f"c1-{r['task']}-{r['config']}-r1".lower()
            f.write(json.dumps({"round": "c1", "case": r["task"], "config": r["config"], "rep": 1, "run": run, "agent": {"outcome": "error" if f"{r['task']}-{r['config']}" in hit else "finished"},
                                "gateway": {"spent_usd": 0.1, "calls": 1, "cap_usd": 0.75, "model_path_failures": 0}, "validator": {"outcome": "not_resolved"}}) + "\n")
            for ext in (".diff", ".verdict.json"): open(f"{tmp}/results/patches/c1/{run}{ext}", "w").write("x")
    for r in opened: open(f"{tmp}/results/patches/c1/{r}.diff", "w").write("")
    open(f"{tmp}/results/budget-c1.jsonl", "w").write('{"rep": 1, "spent_usd": 0.7295, "event": "start", "need_usd": 12.0}\n{"rep": 1, "event": "end", "spent_usd": 3.1928, "cost_usd": 2.4633}\n'
                                                      '{"rep": 2, "spent_usd": 3.1928, "event": "start", "need_usd": 3.07914}\n')
    cmd = [sys.executable, "cases/void_tries.py", "c1", "--why", "test", "--journaled", *[f"c1-{h}-r1".lower() for h in hit], "--opened", *opened, "--drop-budget", "1:end", "2:start"]
    L = lambda n: [json.loads(l) for l in open(f"{tmp}/results/{n}") if l.strip()]
    snap = lambda: {n: open(f"{tmp}/results/{n}").read() for n in ("attempts-c1.jsonl", "voided-c1.jsonl", "infra-c1.jsonl", "budget-c1.jsonl", "budget-c1.voided.jsonl")}
    first = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True); one = snap()
    second = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True); two = snap()
    bad = subprocess.run([sys.executable, "cases/void_tries.py", "c1", "--why", "x", "--journaled", "c1-t9-a-r1"], cwd=tmp, capture_output=True, text=True); three = snap()
    gate = lambda *a, stdin=None: subprocess.run([sys.executable, "cases/budget_gate.py", *a, "c1", "0.75", "1.25"], cwd=tmp, capture_output=True, text=True, input=stdin).stdout.strip()
    state = json.dumps({"spent_usd": 3.1928, "budget_usd": 15.0, "reserved_usd": 0, "halted": None})
    missing, verdict = gate("missing", "1"), gate("decide", "1", stdin=state)
    left = sorted(r["case"] + "-" + r["config"] for r in L("attempts-c1.jsonl")); voided_dir = os.listdir(f"{tmp}/results/patches/c1/voided")
    backups = [x for x in os.listdir(f"{tmp}/results") if "before-void" in x]
    good = (first.returncode == 0 and second.returncode == 0 and one == two == three and bad.returncode == 1
            and left == ["T3-B", "T4-A", "T5-A", "T6-A", "T8-A", "T8-B"] and len(L("voided-c1.jsonl")) == 10 and len(L("infra-c1.jsonl")) == 14
            and [(r["rep"], r["event"]) for r in L("budget-c1.jsonl")] == [(1, "start")] and len(L("budget-c1.voided.jsonl")) == 2
            and len(voided_dir) == 24 and len(backups) == 1 and missing == "10" and verdict == "resume")
    check("5 void_tries.py: the 10 tries leave the journal and are kept, 14 infra records, the gate resumes repetition 1, a second run and an unknown run change nothing", good,
          f"journal left {left}; voided {len(L('voided-c1.jsonl'))}; infra {len(L('infra-c1.jsonl'))}; budget {[(r['rep'], r['event']) for r in L('budget-c1.jsonl')]}; files in voided/ {len(voided_dir)}; "
          f"backups {len(backups)}; gate: missing {missing}, decide {verdict}; second run identical {one == two}; unknown run exit {bad.returncode}")
    shutil.rmtree(tmp, ignore_errors=True)
    return good

def main():
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", UP), Provider).serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="attempt-test-"); lab = f"{tmp}/lab"; os.makedirs(f"{lab}/cases"); os.makedirs(f"{tmp}/state"); os.makedirs(f"{tmp}/srv/T1")
    shutil.copy(f"{ROOT}/cases/attempt_team.sh", f"{lab}/cases/attempt_team.sh")
    open(f"{lab}/cases/pod.py", "w").write(POD_STUB)
    open(f"{lab}/cases/validate.py", "w").write('print(\'VERDICT {"outcome": "resolved"}\')\n')
    open(f"{lab}/tasks.csv", "w").write("T1,stub\n")
    for name in ("meta.json", "failure.txt"): open(f"{tmp}/srv/T1/{name}", "w").write("{}\n")
    for name in ("key", "admin-key"): open(f"{tmp}/{name}", "w").write("fake-" + name)
    genv = dict(os.environ, UPSTREAM=f"http://127.0.0.1:{UP}/v1/messages", KEY_FILE=f"{tmp}/key", ADMIN_KEY_FILE=f"{tmp}/admin-key", STATE_FILE=f"{tmp}/state/budget.json",
                OVERHEAD_TOK="0", PRICES='{"m": [1, 1]}', BUDGET_USD="100", MAX_RUN_USD="10", PORT=str(GW), ADMIN_PORT=str(AD))
    gw = subprocess.Popen([sys.executable, f"{ROOT}/gateway/gateway.py"], env=genv, stdout=subprocess.DEVNULL)
    ok = True
    try:
        for _ in range(50):
            try: urllib.request.urlopen(f"http://127.0.0.1:{GW}/healthz", timeout=1); break
            except Exception: time.sleep(0.1)
        def admin(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{AD}{path}", data=json.dumps(body).encode() if body is not None else None, headers={"Authorization": "Bearer fake-admin-key"})
            try: return json.loads(urllib.request.urlopen(req, timeout=10).read())
            except urllib.error.HTTPError as e: return {"status": e.code}
        env = dict(os.environ, HOME=tmp, CAP_USD="1", ADMIN=f"http://127.0.0.1:{AD}", ADMIN_KEY_FILE=f"{tmp}/admin-key", CASES_DIR=f"{tmp}/srv", STUB_GW=f"http://127.0.0.1:{GW}", CLOSE_RETRY_S="0")
        def attempt(cfg):
            p = subprocess.run(["bash", f"{lab}/cases/attempt_team.sh", "c9", "T1", cfg, "1"], env=env, capture_output=True, text=True)
            return p.returncode, (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        rows = lambda name: [json.loads(l) for l in open(f"{lab}/results/{name}") if l.strip()] if os.path.exists(f"{lab}/results/{name}") else []
        def check(name, cond, detail):
            nonlocal ok; ok &= bool(cond); print("PASS" if cond else "FAIL", name, "-", detail, flush=True)

        rc, last = attempt("A"); j = rows("attempts-c9.jsonl")
        check("1 a normal attempt is journaled with the validator's verdict",
              rc == 0 and len(j) == 1 and j[0]["run"] == "c9-t1-a-r1" and j[0]["agent"]["outcome"] == "finished" and j[0]["validator"]["outcome"] == "resolved", f"exit {rc}; journal {[(r['run'], r['agent']['outcome'], r['validator'].get('outcome')) for r in j]}")

        MODE["v"] = "nocredit"; rc, last = attempt("B"); j = rows("attempts-c9.jsonl"); inf = rows("infra-c9.jsonl"); st = admin("/state")
        check("2 the provider refuses the account during a run: not journaled (a partial patch is not a result), kept in the infra file, gateway halted",
              rc == 1 and len(j) == 1 and len(inf) == 1 and inf[0]["run"] == "c9-t1-b-r1" and "provider_billing" in inf[0]["reason"]
              and inf[0]["gateway"]["model_path_failure_reasons"] == {"provider_billing": 1} and inf[0]["agent"].get("outcome") == "error"
              and not os.path.exists(f"{lab}/results/patches/c9/c9-t1-b-r1.diff") and "provider_billing" in (st.get("halted") or ""),
              f"exit {rc}; journal lines {len(j)}; infra {[(r['run'], r['reason'][:60], r['gateway']['model_path_failure_reasons']) for r in inf]}; halted: {st.get('halted')}; last line: {last}")

        rc, last = attempt("B"); inf2 = rows("infra-c9.jsonl"); opened = admin("/runs/c9-t1-b-r1-t2")
        check("3 while the gateway is halted an attempt is not started: no run opened, no infrastructure try used",
              rc == 1 and len(inf2) == 1 and len(rows("attempts-c9.jsonl")) == 1 and opened == {"status": 404} and "halted" in last[0], f"exit {rc}; infra lines {len(inf2)}; run -t2 on the gateway: {opened}; last line: {last}")

        MODE["v"] = "ok"; resumed = admin("/resume", {}); rc, last = attempt("B"); j = rows("attempts-c9.jsonl")
        check("4 after POST /resume the attempt is redone under a new run id and journaled",
              resumed.get("halted", 1) is None and rc == 0 and [r["run"] for r in j] == ["c9-t1-a-r1", "c9-t1-b-r1-t2"] and j[1]["validator"]["outcome"] == "resolved" and len(rows("infra-c9.jsonl")) == 1,
              f"resume {resumed}; exit {rc}; journal {[r['run'] for r in j]}")
        ok &= void_check(check)
    finally:
        gw.terminate(); gw.wait(); shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
