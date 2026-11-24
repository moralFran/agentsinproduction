#!/usr/bin/env python3
"""
Takes tries that were journaled as attempts by mistake out of the journal, keeping everything (criteria.md E20,
written for the incident of 2026-11-16: the provider's account ran out of credit and the gateway of that day did not
book the refusals to the runs). Runs ON the lab VM, from the experiment's folder, with the collection stopped.

  void_tries.py <round> --why "<reason>" [--journaled <run> ...] [--opened <run> ...] [--drop-budget <rep>:<event> ...]

  --journaled  runs that are in results/attempts-<round>.jsonl. Each line leaves the journal and goes, unchanged plus
               the reason, to results/voided-<round>.jsonl; its patch and verdict files move to
               results/patches/<round>/voided/; one record is appended to results/infra-<round>.jsonl, so the runner
               counts one infrastructure try and redoes the attempt under a new run id (-t2).
  --opened     run ids that were opened on the gateway and never journaled (the gateway refuses a reused id). Only the
               infra record is written, and the empty patch file moves to voided/.
  --drop-budget  records of results/budget-<round>.jsonl written from the wrong picture (e.g. 1:end 2:start); they move
               to results/budget-<round>.voided.jsonl. The start record of a repetition stays, so its cost still
               counts everything the gateway booked since then, voided tries included.
The journal as it was is copied first to results/attempts-<round>.before-void-<UTC time>.jsonl. Nothing is deleted.
Running it again with the same arguments changes nothing. A --journaled run that is neither in the journal nor
already voided stops the script before anything is written.
"""
import argparse, json, os, re, shutil, sys, time


def rows(p): return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def write_all(p, items):
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in items)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)


def append(p, items):
    if not items: return
    with open(p, "a") as f:
        f.write("".join(json.dumps(r) + "\n" for r in items)); f.flush(); os.fsync(f.fileno())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("round"); ap.add_argument("--why", required=True)
    ap.add_argument("--journaled", nargs="*", default=[]); ap.add_argument("--opened", nargs="*", default=[])
    ap.add_argument("--drop-budget", nargs="*", default=[]); ap.add_argument("--base", default="results")
    a = ap.parse_args()
    b, rnd, now = a.base, a.round, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    jp, ip, vp, bp = f"{b}/attempts-{rnd}.jsonl", f"{b}/infra-{rnd}.jsonl", f"{b}/voided-{rnd}.jsonl", f"{b}/budget-{rnd}.jsonl"
    journal, infra, voided = rows(jp), rows(ip), rows(vp)
    in_journal = {r["run"] for r in journal}; in_infra = {r["run"] for r in infra}; in_voided = {r["run"] for r in voided}
    lost = [r for r in a.journaled if r not in in_journal and r not in in_voided]
    if lost: sys.exit(f"not in the journal and not voided before: {lost}; nothing was changed")
    both = sorted(set(a.journaled) & set(a.opened))
    if both: sys.exit(f"named as journaled and as opened: {both}; nothing was changed")
    journaled_opened = [r for r in a.opened if r in in_journal]
    if journaled_opened: sys.exit(f"--opened runs that ARE in the journal: {journaled_opened}; nothing was changed")
    parsed = {}
    for r in a.opened:
        m = re.fullmatch(re.escape(rnd.lower()) + r"-(t\d+)-([ab])-r(\d+)", r)
        if not m: sys.exit(f"cannot read task, configuration and repetition from run id {r}; nothing was changed")
        parsed[r] = {"case": m.group(1).upper(), "config": m.group(2).upper(), "rep": int(m.group(3))}
    drops = set()
    for d in a.drop_budget:
        m = re.fullmatch(r"(\d+):(start|end|not_started)", d)
        if not m: sys.exit(f"--drop-budget takes <rep>:<start|end|not_started>, got {d}; nothing was changed")
        drops.add((int(m.group(1)), m.group(2)))

    take = [r for r in journal if r["run"] in set(a.journaled)]
    if take:
        shutil.copy2(jp, f"{b}/attempts-{rnd}.before-void-{now}.jsonl")
        append(vp, [r | {"voided_at": now, "voided_why": a.why} for r in take])
    new_infra = [{"round": rnd, "case": r["case"], "config": r["config"], "rep": r["rep"], "run": r["run"], "reason": a.why, "at": round(time.time()),
                  "agent": r.get("agent", {}), "agent_pod": r.get("agent_pod", {}),
                  "gateway": {k: r.get("gateway", {}).get(k) for k in ("spent_usd", "calls", "cap_usd", "model_path_failures")} | {"model_path_failure_reasons": None},
                  "was_journaled": True, "validator_said": r.get("validator", {}).get("outcome")}
                 for r in take if r["run"] not in in_infra]
    new_infra += [{"round": rnd, **parsed[r], "run": r, "reason": a.why, "at": round(time.time()), "agent": {}, "agent_pod": {},
                   "gateway": {"spent_usd": None, "calls": None, "cap_usd": None, "model_path_failures": None, "model_path_failure_reasons": None},
                   "was_journaled": False}
                  for r in a.opened if r not in in_infra]
    append(ip, new_infra)                                 # the infra record first: a crash here leaves a run that is skipped, not one that is spent twice
    if take: write_all(jp, [r for r in journal if r["run"] not in set(a.journaled)])
    pd = f"{b}/patches/{rnd}"; moved = 0
    for r in list(a.journaled) + list(a.opened):
        for ext in (".diff", ".verdict.json"):
            src = f"{pd}/{r}{ext}"
            if os.path.exists(src):
                os.makedirs(f"{pd}/voided", exist_ok=True); os.replace(src, f"{pd}/voided/{r}{ext}"); moved += 1
    budget = rows(bp); out = [r for r in budget if (r.get("rep"), r.get("event")) in drops]
    if out:
        append(f"{b}/budget-{rnd}.voided.jsonl", [r | {"voided_at": now, "voided_why": a.why} for r in out])
        write_all(bp, [r for r in budget if (r.get("rep"), r.get("event")) not in drops])
    print(f"journal: {len(take)} line(s) moved to {vp}, {len(journal) - len(take)} left; infra records added: {len(new_infra)}; "
          f"patch/verdict files moved: {moved}; budget records moved: {len(out)}")


if __name__ == "__main__":
    main()
