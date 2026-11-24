#!/usr/bin/env python3
"""Runs ON aip-ctx-01. Blind review packets of experiment 05 (criteria.md E21): one Markdown file per attempt the validator
called `resolved`. A packet shows the task (number, areas, the statement the agent received), the commit's test files, the
validator's summary, the agent's patch and the owner's commit (code only, secret/<T#>/fix-source.diff), with a file and
line count of each. It never shows the configuration, the repetition, the run id, cost, calls, time, or the agent's and
the reviewer's final text. Packet ids are random, packets are written in a random order and every file gets the same
modification time. The key (packet -> run) goes to <out>/key.jsonl (mode 600) and is not to be opened before every packet
has a verdict. Refuses to run twice: the pool is built once, after the round is complete.

  usage: blind_team.py <round-id> [--journal F] [--patches DIR] [--cases DIR] [--secret DIR] [--out DIR]
Defaults: results/attempts-<round>.jsonl, results/patches/<round>, /srv/ci/cases, /srv/ci/secret, results/blind."""
import json, os, pathlib, random, re, secrets, sys

H_TASK = "## A tarefa (o enunciado que o agente recebeu)"
H_PATCH = "## Patch do agente"
H_FIX = "## Meu commit (o gabarito: só o código; os testes já estavam na caixa)"
MTIME = 1794787200   # 2026-11-16T00:00:00Z on every packet


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def stat(diff):
    """(files, added, removed) of a unified diff."""
    files = len(re.findall(r"^diff --git ", diff, re.M))
    add = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    rem = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return files, add, rem


def fence(text):
    """A fence longer than any run of backticks inside the text, so a diff that contains ``` cannot close it."""
    n = max([3] + [len(m) + 1 for m in re.findall(r"`{3,}", text)])
    return "`" * n


def packet(pid, r, meta, patch, fix):
    v = r["validator"]; s2 = v.get("stage2") or {}
    pf, pa, pr = stat(patch); ff, fa, fr = stat(fix)
    checks = (f"validador de caminhos ok; {v['f2p_total']} casos que deviam passar a passar: todos 3/3; "
              f"suíte da área ({', '.join(s2.get('jobs', [])) or 'sem área em escopo'}): {v['p2p_total']} casos que deviam continuar passando, "
              f"quebrados {len(v.get('broken', []))}, instáveis na tentativa {len(v.get('unstable_in_attempt', []))}, "
              f"dependentes do ambiente {len(v.get('environment_dependent', []))}")
    fp, ff_ = fence(patch), fence(fix)
    return (f"# Pacote {pid}\n\n- Tarefa: {meta['id']} · {', '.join(meta['areas'])}\n"
            f"- Testes do commit: {', '.join(meta['test_files'])}\n"
            f"- Verificações obrigatórias: {checks}\n"
            f"- Tamanho: patch do agente {pf} arquivo(s), +{pa} −{pr}; meu commit {ff} arquivo(s), +{fa} −{fr}\n\n"
            f"Julgar com os critérios do protocolo: equivalente / válida / pior / inconclusiva.\n\n"
            f"{H_TASK}\n\n{meta['statement'].strip()}\n\n"
            f"{H_PATCH}\n{fp}diff\n{patch.rstrip()}\n{fp}\n\n{H_FIX}\n{ff_}diff\n{fix.rstrip()}\n{ff_}\n")


LEAK = re.compile(r"\b[a-z]\d+-t\d-[ab]-r\d\b|ag-c\d|\bconfig(uração)? [AB]\b|\brepetição \d\b|\brep(etition)? ?\d\b", re.I)


def main():
    rnd = sys.argv[1]
    journal = opt("--journal", f"results/attempts-{rnd}.jsonl"); patches = pathlib.Path(opt("--patches", f"results/patches/{rnd}"))
    cases = pathlib.Path(opt("--cases", "/srv/ci/cases")); secret = pathlib.Path(opt("--secret", "/srv/ci/secret"))
    out = pathlib.Path(opt("--out", "results/blind")); pk = out / "packets"
    if (out / "key.jsonl").exists(): sys.exit(f"{out}/key.jsonl exists: the pool was already built; it is built once")
    rows = [json.loads(l) for l in open(journal) if l.strip()]
    ok = [r for r in rows if r["validator"].get("outcome") == "resolved"]
    random.SystemRandom().shuffle(ok)
    pk.mkdir(parents=True, exist_ok=True)
    key, used, empty = [], set(), []
    for r in ok:
        patch = (patches / f"{r['run']}.diff").read_text(errors="replace")
        if not patch.strip(): empty.append(r["run"]); continue
        meta = json.load(open(cases / r["case"] / "meta.json"))
        fix = (secret / r["case"] / "fix-source.diff").read_text(errors="replace")
        while True:
            pid = secrets.token_hex(4)
            if pid not in used: used.add(pid); break
        (pk / f"{pid}.md").write_text(packet(pid, r, meta, patch, fix))
        os.utime(pk / f"{pid}.md", (MTIME, MTIME))
        key.append({"packet": pid, "run": r["run"], "round": rnd, "case": r["case"], "config": r["config"], "rep": r["rep"]})
    random.SystemRandom().shuffle(key)
    fd = os.open(out / "key.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f: f.write("".join(json.dumps(k) + "\n" for k in key))
    # leak check on everything outside the two diffs (their content is the app's code and may say anything)
    leaks = []
    for f in sorted(pk.glob("*.md")):
        s = f.read_text(); head = s[:s.index(H_PATCH)]
        if LEAK.search(head): leaks.append(f.name)
    per_task = {}
    for k in key: per_task[k["case"]] = per_task.get(k["case"], 0) + 1
    print(f"{len(key)} packets from {len(ok)} resolved attempts of {len(rows)} in the journal; per task: "
          + ", ".join(f"{t} {n}" for t, n in sorted(per_task.items()))
          + f"; resolved with an empty patch (no packet): {empty or 'none'}; packets whose header mentions a run id, configuration or repetition: {len(leaks)} {leaks[:5]}")
    if leaks: sys.exit(1)


if __name__ == "__main__":
    main()
