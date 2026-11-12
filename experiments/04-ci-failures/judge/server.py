#!/usr/bin/env python3
"""Blind judging page for experiment 04 (V5). Local only (127.0.0.1).

Shows one packet at a time (the failure, the agent's patch, the maintainer's fix, the hidden-test result) and records
the reviewer's verdict, including Codex decisions explicitly delegated by Francisco. It never opens key.jsonl:
which version or round wrote a patch stays unknown here.

  server.py <packets_dir> <verdicts.jsonl> [port]     start the page
  server.py <packets_dir> <verdicts.jsonl> --summary  print the tally and write verdicts.csv next to the jsonl

Optional files next to verdicts.jsonl: excluded.json ({project: reason}; those packets leave the main analysis and need no
verdict) and second-opinion.jsonl (one record per packet with verdict, note, reviewer: shown as a second opinion).

verdicts.jsonl is append-only: one line per click, the latest line per packet wins. Packets that failed the maintainer's
hidden tests are "pior" by the protocol's rule (source "rule"); they are shown but need no click.
"""
import csv, hashlib, html, json, pathlib, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

H_FAIL = "## A falha (fim da saída, na nossa reprodução)"
H_PATCH = "## Patch do agente"
H_FIX = "## Correção do mantenedor (inclui as mudanças em teste, quando houve)"
VERDICTS = ("equivalente", "valida", "pior", "inconclusiva")


def unfence(block):
    lines = block.strip("\n").split("\n")
    if lines and lines[0].startswith("```"): lines = lines[1:]
    if lines and lines[-1].strip() == "```": lines = lines[:-1]
    return "\n".join(lines)


def load_packets(d, excluded=None, second=None):
    excluded, second = excluded or {}, second or {}
    out = []
    for f in sorted(pathlib.Path(d).glob("*.md")):
        s = f.read_text(errors="replace")
        i, j, k = s.index(H_FAIL), s.index(H_PATCH), s.index(H_FIX)
        assert i < j < k, f.name
        head = s[:i]
        g = lambda label: (re.search(rf"^- {label}: (.*)$", head, re.M) or [None, ""])[1].strip()
        hidden_txt = g("Testes ocultos")
        hidden = "fail" if hidden_txt.startswith("FALHOU") else "pass" if hidden_txt.startswith("passou") else "none"
        patch = unfence(s[j + len(H_PATCH):k])
        out.append({"id": f.stem, "project": g("Projeto"), "command": g("Comando de teste").strip("`"), "checks": g("Verificações obrigatórias"),
                    "hidden": hidden, "hidden_txt": hidden_txt, "failure": unfence(s[i + len(H_FAIL):j]), "patch": patch,
                    "fix": unfence(s[k + len(H_FIX):]), "patch_hash": hashlib.sha256(patch.strip().encode()).hexdigest()[:12]})
    for p in out:
        p["excluded"] = next((why for proj, why in excluded.items() if p["project"].startswith(proj)), "")
        s2 = second.get(p["id"])
        p["second"] = {"verdict": s2.get("verdict", ""), "note": s2.get("note", ""), "reviewer": s2.get("reviewer", ""), "source": s2.get("source", "")} if s2 else None
    out.sort(key=lambda p: (bool(p["excluded"]), p["project"].lower(), p["id"]))   # same case together; excluded cases last
    return out


def load_verdicts(path):
    v = {}
    p = pathlib.Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                r = json.loads(line); v[r["packet"]] = r
    return v


def merged(packets, verdicts):
    """Use the protocol's rule, otherwise the latest attributed judgment."""
    out = {}
    for p in packets:
        if p["excluded"]:
            out[p["id"]] = {"packet": p["id"], "verdict": "fora", "source": "excluded", "note": p["excluded"]}
        elif p["hidden"] == "fail":
            out[p["id"]] = {"packet": p["id"], "verdict": "pior", "source": "rule", "note": "falhou nos testes ocultos do mantenedor"}
        elif p["id"] in verdicts:
            out[p["id"]] = dict(verdicts[p["id"]], source=verdicts[p["id"]].get("source", "human"))
    return out


def summary(packets, verdicts, csv_path=None):
    m = merged(packets, verdicts)
    tally = {}
    for p in packets:
        key = m[p["id"]]["verdict"] if p["id"] in m else "pendente"
        tally[key] = tally.get(key, 0) + 1
    if csv_path:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["packet", "project", "hidden_tests", "verdict", "source", "note", "second_opinion", "second_opinion_shown", "reviewer", "user_delegated"])
            for p in packets:
                r = m.get(p["id"], {})
                w.writerow([p["id"], p["project"], p["hidden"], r.get("verdict", ""), r.get("source", ""), r.get("note", ""), (p["second"] or {}).get("verdict", ""), r.get("second_opinion_shown", ""), r.get("reviewer", ""), r.get("user_delegated", "")])
    return tally


PAGE = pathlib.Path(__file__).with_name("page.html")


class Handler(BaseHTTPRequestHandler):
    packets = []; vpath = ""

    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE.read_bytes(), "text/html")
        if self.path == "/api/state":
            v = load_verdicts(self.vpath)
            return self.send(200, json.dumps({"packets": self.packets, "verdicts": merged(self.packets, v), "tally": summary(self.packets, v)}))
        self.send(404, "{}")

    def do_POST(self):
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80: hosts |= {"127.0.0.1", "localhost"}
        if self.path != "/api/verdict" or host not in hosts:
            return self.send(404, "{}")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.send(415, json.dumps({"error": "Content-Type must be application/json"}))
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + host:
            return self.send(403, json.dumps({"error": "cross-origin verdict submission refused"}))
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384: return self.send(400, "{}")
            r = json.loads(self.rfile.read(size))
            if not isinstance(r, dict): return self.send(400, "{}")
        except (ValueError, UnicodeError): return self.send(400, "{}")
        p = next((x for x in self.packets if x["id"] == r.get("packet")), None)
        if not p or r.get("verdict") not in VERDICTS: return self.send(400, json.dumps({"error": "pacote ou veredito inválido"}))
        if p["excluded"]: return self.send(400, json.dumps({"error": "este pacote está fora da análise principal"}))
        if p["hidden"] == "fail": return self.send(400, json.dumps({"error": "este pacote já é 'pior' pela regra do protocolo"}))
        source = r.get("source", "human")
        if source not in ("human", "codex_delegated"):
            return self.send(400, json.dumps({"error": "origem do julgamento inválida"}))
        if source == "codex_delegated" and r.get("user_delegated") is not True:
            return self.send(400, json.dumps({"error": "julgamento delegado exige delegação explícita"}))
        rec = {"packet": p["id"], "verdict": r["verdict"], "note": str(r.get("note", ""))[:2000], "patch_hash": p["patch_hash"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "second_opinion_shown": bool(p["second"]), "second_opinion": (p["second"] or {}).get("verdict", ""),
               "source": source, "reviewer": "Codex" if source == "codex_delegated" else "Francisco", "user_delegated": source == "codex_delegated"}
        with open(self.vpath, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        v = load_verdicts(self.vpath); summary(self.packets, v, pathlib.Path(self.vpath).with_suffix(".csv"))
        self.send(200, json.dumps({"ok": True, "verdicts": merged(self.packets, v), "tally": summary(self.packets, v)}))


if __name__ == "__main__":
    pk, vp = sys.argv[1], sys.argv[2]
    side = pathlib.Path(vp).parent
    excluded = json.loads((side / "excluded.json").read_text()) if (side / "excluded.json").exists() else {}
    second = {}
    if (side / "second-opinion.jsonl").exists():
        for line in (side / "second-opinion.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line); second[r["packet"]] = r
    packets = load_packets(pk, excluded, second)
    if len(sys.argv) > 3 and sys.argv[3] == "--summary":
        t = summary(packets, load_verdicts(vp), pathlib.Path(vp).with_suffix(".csv"))
        print(f"{len(packets)} pacotes:", ", ".join(f"{k} {v}" for k, v in sorted(t.items()))); sys.exit(0)
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8791
    Handler.packets, Handler.vpath = packets, vp
    print(f"{len(packets)} pacotes; vereditos em {vp}; abra http://127.0.0.1:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
