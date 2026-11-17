#!/usr/bin/env python3
"""Runs ON aip-ci-01. Blind review packets for Francisco: one Markdown file per agent patch that passed the mandatory
checks and stayed green 3/3 (outcomes green_passes_hidden and green_no_hidden_tests), plus the green patches that failed
the maintainer's hidden tests (protocol: those are judged too). Each packet shows the case, the failure, the agent's patch
and the maintainer's fix side by side, and the hidden-test result; never the round, the version, the run id or the
repetition. Packet ids are random. The key (packet -> run) is written to results/blind/key.jsonl and must not be opened
before the judging; packets of later rounds join the same pool, so the review should happen once v2 is in.
usage: blind.py <round-id>..."""
import json, os, secrets, sys
import os as _os, sys as _sys
if _os.path.exists("ARCHIVE") and _os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": _sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
OK = ("green_passes_hidden", "green_no_hidden_tests", "green_fails_hidden")
os.makedirs("results/blind/packets", exist_ok=True)
key = {}
if os.path.exists("results/blind/key.jsonl"):
    for l in open("results/blind/key.jsonl"): k = json.loads(l); key[k["run"]] = k["packet"]
new = 0
for rnd in sys.argv[1:]:
    for l in open(f"results/attempts-{rnd}.jsonl"):
        r = json.loads(l); out = r["executor"].get("outcome")
        if out not in OK or r["run"] in key: continue
        pid = secrets.token_hex(3); key[r["run"]] = pid; new += 1
        with open("results/blind/key.jsonl", "a") as k: k.write(json.dumps({"packet": pid, "run": r["run"], "round": rnd}) + "\n")
        cid = r["case"]; meta = json.load(open(f"/srv/ci/secret/{cid}/meta.json"))
        failure = open(f"/srv/ci/cases/{cid}/failure.txt").read().strip().splitlines()[-40:]
        patch = open(f"results/patches/{rnd}/{r['run']}.diff").read()
        fix = open(f"/srv/ci/secret/{cid}/fix.diff").read()
        hidden = {"green_passes_hidden": "passou nos testes ocultos do mantenedor", "green_no_hidden_tests": "o caso não tem testes ocultos",
                  "green_fails_hidden": "FALHOU nos testes ocultos do mantenedor (pela regra do protocolo, isso é \"pior\")"}[out]
        open(f"results/blind/packets/{pid}.md", "w").write(
            f"# Pacote {pid}\n\n- Projeto: {meta['repo']} ({meta['language']})\n- Comando de teste: `{meta['test_cmd']}`\n"
            f"- Verificações obrigatórias: aplicou; o executor não viu mudança em teste, CI, configuração ou dependências; suíte original verde 3/3\n"
            f"- Testes ocultos: {hidden}\n\n"
            f"Julgar com os critérios do protocolo: equivalente / válida / pior / inconclusiva.\n\n"
            f"## A falha (fim da saída, na nossa reprodução)\n```\n" + "\n".join(failure) + "\n```\n\n"
            f"## Patch do agente\n```diff\n{patch}\n```\n\n## Correção do mantenedor (inclui as mudanças em teste, quando houve)\n```diff\n{fix}\n```\n")
print(f"{new} new packets; {len(key)} in the pool")
