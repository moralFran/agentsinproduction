#!/usr/bin/env python3
"""The funnel of the case set: repositories examined -> candidates -> settled -> reproduced, with a count per exclusion
reason at each step. Reads the miner's logs (mining/candidates-*.log, the corrected runs; the first run with the log
download bug is in mining/run1-log-download-bug/ and is not counted), the recheck, the preparation and reproduction
records. Writes cases/funnel.md and prints it."""
import collections, json, pathlib, re
lines = [json.loads(l) for f in ("mining/candidates-go.log", "mining/candidates-python.log") for l in open(f)]
lang_of = {}
for f, lg in (("mining/candidates-go.log", "Go"), ("mining/candidates-python.log", "Python")):
    for l in open(f): lang_of[json.loads(l)["repo"]] = lg
repos = {r["repo"] for r in lines}
repo_drop = collections.Counter(re.sub(r"\(.*", "", r["verdict"]).strip() for r in lines if r["item"] == "repo")
cand_drop = collections.Counter(re.sub(r"\(.*|: job .*", "", r["verdict"]).strip() for r in lines if r["item"] != "repo" and r["verdict"] != "candidate")
cands = [json.loads(l) for f in ("mining/candidates-go.jsonl", "mining/candidates-python.jsonl") for l in open(f)]
cid = lambda c: re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
rechk = set(open("cases/excluded-recheck.txt").read().split())
prep = {}
for l in open("cases/prep-out/prep.jsonl"):
    m = re.search(r'"id": "([^"]+)"', l) or re.search(r"PREP_FAIL ([^:]+):", l)
    if m: prep[m.group(1)] = l
rep = {json.loads(l)["id"]: json.loads(l) for l in open("cases/repro.jsonl")}
review_path = pathlib.Path('cases/eligibility-at-freeze.json')
eligibility = json.loads(review_path.read_text()) if review_path.exists() else {}
step = collections.Counter(); per_lang = collections.Counter(); why_prep = collections.Counter()
for c in cands:
    i = cid(c)
    if i in rechk: step["excluded: fix touches only test files (snapshot/golden, recheck)"] += 1; continue
    if eligibility.get(i, {}).get('decision') == 'exclude':
        step['excluded: eligibility review'] += 1; continue
    if i in rep:
        v = rep[i]["verdict"]; step[v] += 1
        if v == "reproduced": per_lang[c["language"]] += 1
        continue
    if i in prep and ('"fail"' in prep[i] or "PREP_FAIL" in prep[i]):
        w = (re.search(r'"why": "([^"]+)"', prep[i]) or re.search(r"PREP_FAIL [^:]+: (.{0,60})", prep[i]))
        why_prep[re.sub(r":.*", "", w.group(1)) if w else "?"] += 1; step["preparation failed"] += 1; continue
    step["not settled yet"] += 1
md = ["# Funil dos casos (gerado por `cases/funnel.py`)", "",
      f"- Repositórios examinados: **{len(repos)}** (Go {sum(1 for r in repos if lang_of[r] == 'Go')}, Python {sum(1 for r in repos if lang_of[r] == 'Python')})",
      "- Repositórios descartados antes de olhar as falhas:"] + [f"  - {k}: {v}" for k, v in repo_drop.most_common()] + [
      "- Pares falha → correção examinados e descartados:"] + [f"  - {k}: {v}" for k, v in cand_drop.most_common()] + [
      f"- **Candidatos:** {len(cands)} (Go {sum(c['language'] == 'Go' for c in cands)}, Python {sum(c['language'] == 'Python' for c in cands)})",
      "- Destino de cada candidato:"] + [f"  - {k}: {v}" for k, v in step.most_common()] + [
      "- Falhas de preparação por motivo:"] + [f"  - {k}: {v}" for k, v in why_prep.most_common()] + [
      f"- **Reproduzidos (3/3 quebrado falha, 3/3 correção passa):** {sum(per_lang.values())} (Go {per_lang['Go']}, Python {per_lang['Python']})"]
open("cases/funnel.md", "w").write("\n".join(md) + "\n"); print("\n".join(md))
