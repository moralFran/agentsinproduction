#!/usr/bin/env python3
"""Final tally of experiment 04 (V5). Joins the attempts of v1 and v2, the blind verdicts and, only here, the key that
says which packet came from which run. Run only after every packet has a verdict and the exclusions are decided
(amendments 24–27).   usage: analyze.py   (from the experiment folder; writes results/final-summary.md and final.json)"""
import collections, csv, json, pathlib
# Post-collection: every executor/agent stop is counted without looking for a nonexistent blind packet.
EXTRA = ["patch não aplica", "rejeitado pelo validador", "suíte alterou a árvore", "CI intermitente", "testes ocultos não aplicam",
         "testes ocultos intermitentes", "erro de infraestrutura", "parou por tempo", "parou por limite de ferramentas",
         "erro do agente", "resultado desconhecido"]


def final(a, key, verd):
    ex = (a.get("executor") or {}).get("outcome")
    ag = (a.get("agent") or {}).get("outcome")
    labels = {"ci_still_red": "ainda vermelho", "did_not_apply": "patch não aplica",
              "rejected_by_validator": "rejeitado pelo validador", "test_changed_tree": "suíte alterou a árvore", "ci_flaky_after_patch": "CI intermitente",
              "hidden_tests_did_not_apply": "testes ocultos não aplicam", "hidden_tests_flaky": "testes ocultos intermitentes",
              "infra_error": "erro de infraestrutura", "timeout": "parou por tempo", None: "erro de infraestrutura"}
    if ex in labels: return labels[ex]
    if ex == "no_patch":
        return {"budget_exhausted": "parou por orçamento", "timeout": "parou por tempo",
                "max_tool_calls": "parou por limite de ferramentas", "error": "erro do agente",
                "no_result": "erro de infraestrutura", "finished": "desistiu"}.get(ag, "resultado desconhecido")
    if ex == "green_fails_hidden": return "pior"
    if ex not in ("green_passes_hidden", "green_no_hidden_tests"): return "resultado desconhecido"
    packet = key.get(a["run"]); v = verd.get(packet, {})
    if v.get("verdict") not in ("equivalente", "valida", "pior", "inconclusiva"):
        raise ValueError(f"missing or invalid blind verdict for green run {a['run']}")
    return v["verdict"]


def spent(a):
    value = (a.get("gateway") or {}).get("spent_usd")
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def main():
    R = pathlib.Path("results")
    EXCL = json.load(open(R / "blind/excluded.json"))
    cases = {r["case_id"]: r for r in csv.DictReader(open("cases/cases.csv"))}
    repo = lambda cid: cases[cid]["repo"]
    excluded = lambda cid: any(repo(cid).startswith(k) for k in EXCL)
    attempts = [json.loads(l) for v in ("v1", "v2") for l in open(R / f"attempts-{v}.jsonl")]
    counts = collections.Counter(a["round"] for a in attempts)
    count_label = (f"todas as {counts['v1']} tentativas por versão" if counts['v1'] == counts['v2']
                   else f"todas as tentativas: v1 {counts['v1']}, v2 {counts['v2']}")
    key = {r["run"]: r["packet"] for r in map(json.loads, open(R / "blind/key.jsonl"))}
    verd = {r["packet"]: r for r in csv.DictReader(open(R / "blind/verdicts.csv"))}

    ORDER = ["equivalente", "valida", "pior", "inconclusiva", "ainda vermelho", "desistiu", "parou por orçamento"]
    main = [a for a in attempts if not excluded(a["case"])]
    side = [a for a in attempts if excluded(a["case"])]
    tab = {v: collections.Counter(final(a, key, verd) for a in main if a["round"] == v) for v in ("v1", "v2")}
    per_case = collections.defaultdict(lambda: {"v1": [], "v2": []})
    for a in sorted(main, key=lambda a: (a["case"], a["round"], a["rep"])): per_case[repo(a["case"])][a["round"]].append(final(a, key, verd))
    cost = {v: sum((spent(a) or 0.0) for a in attempts if a["round"] == v) for v in ("v1", "v2")}
    cost_main = {v: sum((spent(a) or 0.0) for a in main if a["round"] == v) for v in ("v1", "v2")}
    fix = lambda c: c["equivalente"] + c["valida"]
    green = lambda c: c["equivalente"] + c["valida"] + c["pior"] + c["inconclusiva"]
    # "pior" split: failed the maintainer's hidden tests (rule) vs passed everything and was judged worse
    pior_kind = {v: collections.Counter(("falhou nos testes ocultos" if a["executor"]["outcome"] == "green_fails_hidden" else "passou em tudo, julgado pior")
                                        for a in main if a["round"] == v and final(a, key, verd) == "pior") for v in ("v1", "v2")}
    side_tab = collections.defaultdict(lambda: {"v1": collections.Counter(), "v2": collections.Counter()})
    for a in side: side_tab[repo(a["case"])][a["round"]][(a.get("executor") or {}).get("outcome", "infra_error") if (a.get("agent") or {}).get("outcome") != "budget_exhausted" else "budget_exhausted"] += 1
    src = collections.Counter(v["source"] for p, v in verd.items() if v["verdict"] and v["source"] != "excluded")

    ORDER += [label for label in EXTRA if any(tab[v][label] for v in tab)]
    unknown_cost = [a["run"] for a in attempts if spent(a) is None]

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
          f"- Custo de API ({count_label}): v1 US$ {cost['v1']:.3f}, v2 US$ {cost['v2']:.3f}; só os casos da análise principal: v1 US$ {cost_main['v1']:.3f}, v2 US$ {cost_main['v2']:.3f}.",
          f"- US$ por correção (análise principal, tentativas falhas incluídas): v1 {cost_main['v1'] / max(1, fix(tab['v1'])):.3f}, v2 {cost_main['v2'] / max(1, fix(tab['v2'])):.3f}.",
          f"- Origem dos vereditos dos pacotes da análise principal: {dict(src)}.", "",
          "## Por caso (r1 / r2 / r3)", "", "| Caso | v1 | v2 |", "|---|---|---|"]
    L += [f"| {c} | {' / '.join(d['v1'])} | {' / '.join(d['v2'])} |" for c, d in sorted(per_case.items())]
    L += ["", "## Fora da análise principal (o mantenedor consertou o teste, não o código)", "", "| Caso | v1 (desfecho do executor) | v2 |", "|---|---|---|"]
    L += [f"| {c} | {dict(d['v1'])} | {dict(d['v2'])} |" for c, d in sorted(side_tab.items())]
    if unknown_cost:
        L += ["", f"- Custo indisponível em {len(unknown_cost)} tentativas: os custos acima somam apenas os valores conhecidos (limite inferior)."]
    (R / "final-summary.md").write_text("\n".join(L) + "\n")
    json.dump({"main_cases": sorted(per_case), "table": {v: dict(tab[v]) for v in tab}, "per_case": per_case, "cost_all": cost, "cost_main": cost_main,
               "pior_kind": {v: dict(pior_kind[v]) for v in pior_kind}, "side": {c: {v: dict(d[v]) for v in d} for c, d in side_tab.items()}, "verdict_sources": dict(src), **({"unknown_cost_runs": unknown_cost} if unknown_cost else {})},
              open(R / "final.json", "w"), indent=1, ensure_ascii=False)
    print("\n".join(L))

if __name__ == "__main__":
    main()
