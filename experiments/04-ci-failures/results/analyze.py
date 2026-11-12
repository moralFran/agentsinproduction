#!/usr/bin/env python3
"""Final tally of experiment 04 (V5). Joins the attempts of v1 and v2, the blind verdicts and, only here, the key that
says which packet came from which run. Run only after every packet has a verdict and the exclusions are decided
(amendments 24–27).   usage: analyze.py   (from the experiment folder; writes results/final-summary.md and final.json)"""
import collections, csv, json, pathlib
R = pathlib.Path("results")
EXCL = json.load(open(R / "blind/excluded.json"))
cases = {r["case_id"]: r for r in csv.DictReader(open("cases/cases.csv"))}
repo = lambda cid: cases[cid]["repo"]
excluded = lambda cid: any(repo(cid).startswith(k) for k in EXCL)
attempts = [json.loads(l) for v in ("v1", "v2") for l in open(R / f"attempts-{v}.jsonl")]
key = {r["run"]: r["packet"] for r in map(json.loads, open(R / "blind/key.jsonl"))}
verd = {r["packet"]: r for r in csv.DictReader(open(R / "blind/verdicts.csv"))}

def final(a):
    """One outcome per attempt. Green patches take the blind verdict; hidden-test failures are 'pior' by rule."""
    ex, ag = a["executor"]["outcome"], a["agent"]["outcome"]
    if ex == "ci_still_red": return "ainda vermelho"
    if ex == "no_patch": return "parou por orçamento" if ag == "budget_exhausted" else "desistiu"
    v = verd[key[a["run"]]]
    assert v["verdict"] in ("equivalente", "valida", "pior", "inconclusiva"), (a["run"], v)
    return v["verdict"]

ORDER = ["equivalente", "valida", "pior", "inconclusiva", "ainda vermelho", "desistiu", "parou por orçamento"]
main = [a for a in attempts if not excluded(a["case"])]
side = [a for a in attempts if excluded(a["case"])]
tab = {v: collections.Counter(final(a) for a in main if a["round"] == v) for v in ("v1", "v2")}
per_case = collections.defaultdict(lambda: {"v1": [], "v2": []})
for a in sorted(main, key=lambda a: (a["case"], a["round"], a["rep"])): per_case[repo(a["case"])][a["round"]].append(final(a))
cost = {v: sum(float(a["gateway"]["spent_usd"]) for a in attempts if a["round"] == v) for v in ("v1", "v2")}
cost_main = {v: sum(float(a["gateway"]["spent_usd"]) for a in main if a["round"] == v) for v in ("v1", "v2")}
fix = lambda c: c["equivalente"] + c["valida"]
green = lambda c: c["equivalente"] + c["valida"] + c["pior"] + c["inconclusiva"]
# "pior" split: failed the maintainer's hidden tests (rule) vs passed everything and was judged worse
pior_kind = {v: collections.Counter(("falhou nos testes ocultos" if a["executor"]["outcome"] == "green_fails_hidden" else "passou em tudo, julgado pior")
                                    for a in main if a["round"] == v and final(a) == "pior") for v in ("v1", "v2")}
side_tab = collections.defaultdict(lambda: {"v1": collections.Counter(), "v2": collections.Counter()})
for a in side: side_tab[repo(a["case"])][a["round"]][a["executor"]["outcome"] if a["agent"]["outcome"] != "budget_exhausted" else "budget_exhausted"] += 1
src = collections.Counter(v["source"] for p, v in verd.items() if v["verdict"] and v["source"] != "excluded")

L = ["# Experimento 04 (V5): resultado final", "",
     f"Análise principal: **{len(per_case)} casos** × 3 repetições × 2 versões = {len(main)} tentativas "
     f"(fora dela, contados à parte: {', '.join(sorted(side_tab))}; emendas 24 e 27).", "",
     "| Desfecho | v1 | v2 |", "|---|---|---|"]
L += [f"| {o} | {tab['v1'][o]} | {tab['v2'][o]} |" for o in ORDER]
L += [f"| **total** | {sum(tab['v1'].values())} | {sum(tab['v2'].values())} |", "",
      f"- Patches verdes (suíte original 3/3, aprovados pelo validador): v1 {green(tab['v1'])}, v2 {green(tab['v2'])}.",
      f"- Correções (equivalente + válida): v1 {fix(tab['v1'])} de {sum(tab['v1'].values())}, v2 {fix(tab['v2'])} de {sum(tab['v2'].values())}.",
      f"- Verdes que não são correção (pior + inconclusiva): v1 {tab['v1']['pior'] + tab['v1']['inconclusiva']} de {green(tab['v1'])}, v2 {tab['v2']['pior'] + tab['v2']['inconclusiva']} de {green(tab['v2'])}.",
      f"- 'Pior' por tipo: v1 {dict(pior_kind['v1'])}; v2 {dict(pior_kind['v2'])}.",
      f"- Custo de API (todas as 33 tentativas por versão): v1 US$ {cost['v1']:.3f}, v2 US$ {cost['v2']:.3f}; só os casos da análise principal: v1 US$ {cost_main['v1']:.3f}, v2 US$ {cost_main['v2']:.3f}.",
      f"- US$ por correção (análise principal, tentativas falhas incluídas): v1 {cost_main['v1'] / max(1, fix(tab['v1'])):.3f}, v2 {cost_main['v2'] / max(1, fix(tab['v2'])):.3f}.",
      f"- Origem dos vereditos dos pacotes da análise principal: {dict(src)}.", "",
      "## Por caso (r1 / r2 / r3)", "", "| Caso | v1 | v2 |", "|---|---|---|"]
L += [f"| {c} | {' / '.join(d['v1'])} | {' / '.join(d['v2'])} |" for c, d in sorted(per_case.items())]
L += ["", "## Fora da análise principal (o mantenedor consertou o teste, não o código)", "", "| Caso | v1 (desfecho do executor) | v2 |", "|---|---|---|"]
L += [f"| {c} | {dict(d['v1'])} | {dict(d['v2'])} |" for c, d in sorted(side_tab.items())]
(R / "final-summary.md").write_text("\n".join(L) + "\n")
json.dump({"main_cases": sorted(per_case), "table": {v: dict(tab[v]) for v in tab}, "per_case": per_case, "cost_all": cost, "cost_main": cost_main,
           "pior_kind": {v: dict(pior_kind[v]) for v in pior_kind}, "side": {c: {v: dict(d[v]) for v in d} for c, d in side_tab.items()}, "verdict_sources": dict(src)},
          open(R / "final.json", "w"), indent=1, ensure_ascii=False)
print("\n".join(L))
