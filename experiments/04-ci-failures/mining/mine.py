#!/usr/bin/env python3
"""Finds candidate cases with the GitHub REST API, read-only, following criteria.md (written before this script).
For each repository returned by the search (stars descending): its push-triggered workflow runs on the default branch,
a failed run immediately followed (next commit, parent == failed commit) by a successful run of the same workflow,
a failed job that is a test job, a fix commit that changes non-test code within the size limits. Every examined
candidate is logged with the reason it was kept or dropped. Token from GH_TOKEN (never written anywhere).
usage: GH_TOKEN=... [EXCLUDE_OWNERS=a,b,...] mine.py <language Go|Python> <max_candidates> [out_dir]"""
import json, os, re, sys, time, urllib.request, urllib.error, urllib.parse

LANG, WANT = sys.argv[1], int(sys.argv[2]); OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(__file__))
TOK = os.environ["GH_TOKEN"]
if os.path.exists(os.path.join(OUT, "..", "ARCHIVE")) and os.environ.get("ALLOW_ARCHIVE_WRITE") != "1": sys.exit("this folder is the historical record (ARCHIVE file): start a fresh run with infra/new-run.sh <new-dir>, or set ALLOW_ARCHIVE_WRITE=1")   # added 2026-11-12, after the collection
def excluded_owners():
    """Repository owners skipped by criteria.md rule 5. EXCLUDE_OWNERS (comma-separated) wins; when it is unset, the
    unversioned file exclude-owners.local next to this script (owners separated by commas or new lines, '#' starts a
    comment line) is read; with neither, only the model provider (anthropics) is excluded."""
    raw = os.environ.get("EXCLUDE_OWNERS")
    if raw is None:
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exclude-owners.local")
        raw = open(f).read() if os.path.exists(f) else "anthropics"
    raw = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    return {o.strip().lower() for o in re.split(r"[,\n]", raw) if o.strip()}
EXCL = excluded_owners()
LIC = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0"}
SINCE = "2025-01-01"
TESTY = re.compile(r"test|pytest|unit", re.I)
NOT_TEST_STEP = re.compile(r"lint|format|fmt|vet|doc|release|coverage|codecov|deploy|install|setup|cache|checkout|upload|download|build image|docker|publish", re.I)
# test files, including test EXPECTATIONS: snapshot files (__snapshots__/, *.snap) and golden files (*.golden, golden/).
# The first version missed snapshots; found by the smoke test on 11/11 (google/osv-scanner: fix and patch were only a .snap)
TESTFILE = re.compile(r"(^|/)(tests?|testdata|testing|__snapshots__|golden|fixtures)(/|$)|_test\.go$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|\.snap$|\.golden$")   # fixtures/ added 12/11 (audit; future runs only)
ENVFILE = re.compile(r"(^|/)(go\.mod|go\.sum|requirements[^/]*\.txt|poetry\.lock|uv\.lock|Pipfile(\.lock)?|setup\.cfg|pyproject\.toml|tox\.ini|noxfile\.py|\.github/.*|Makefile|\.golangci\.ya?ml|\.pre-commit-config\.yaml|Dockerfile|\.tool-versions|\.python-version)$")
log = open(os.path.join(OUT, f"candidates-{LANG.lower()}.log"), "a"); keep = open(os.path.join(OUT, f"candidates-{LANG.lower()}.jsonl"), "a")
calls = 0

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
NOREDIR = urllib.request.build_opener(NoRedirect)

def job_log(full, job_id):
    """Job logs answer with a redirect to blob storage, which rejects our Authorization header (401): follow it by
    hand, without the header (the redirect URL is pre-signed)."""
    global calls; calls += 1
    req = urllib.request.Request(f"https://api.github.com/repos/{full}/actions/jobs/{job_id}/logs", headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json", "User-Agent": "aip-ci-miner"})
    try: NOREDIR.open(req, timeout=60); return ""
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
        if not loc: return ""
    except Exception: return ""                       # network timeout: treated as "log not available"
    try:
        with urllib.request.urlopen(urllib.request.Request(loc, headers={"User-Agent": "aip-ci-miner"}), timeout=120) as r: return r.read().decode("utf-8", "replace")
    except Exception: return ""

def api(path, raw=False):
    global calls
    url = path if path.startswith("http") else "https://api.github.com" + path
    for attempt in range(4):
        calls += 1
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "aip-ci-miner"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read(); return b.decode("utf-8", "replace") if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and "rate limit" in e.read().decode("utf-8", "replace").lower():
                time.sleep(65); continue
            if e.code in (404, 410, 451): return None
            if e.code >= 500: time.sleep(5); continue
            return None
        except Exception: time.sleep(5)
    return None

def L(repo, what, why, **kw):
    log.write(json.dumps({"repo": repo, "item": what, "verdict": why, **kw}) + "\n"); log.flush()

def failing_tests(text):
    t = re.sub(r"^\S+Z ", "", text, flags=re.M)              # strip the timestamps of the job log
    go_pkgs = sorted(set(re.findall(r"^FAIL\s+(\S+)\s+[\d.]+s", t, re.M)))
    go_tests = sorted(set(re.findall(r"--- FAIL: (\S+)", t)))
    py = sorted(set(re.findall(r"^FAILED (\S+?\.py)(?:::(\S+))?", t, re.M)))
    pyver = re.findall(r"(?:Successfully set up CPython|Python version|python-version:)\s*\(?([23]\.\d+(?:\.\d+)?)", t)
    gover = re.findall(r"go version go(\d+\.\d+(?:\.\d+)?)", t)
    return {"go_pkgs": go_pkgs, "go_tests": go_tests[:40], "py_tests": [f"{a}::{b}" if b else a for a, b in py][:40],
            "py_version": pyver[0] if pyver else "", "go_version": gover[0] if gover else ""}

found, per_repo = 0, {}
# a resumed search skips repositories an earlier pass already examined (they are in the log with their verdicts)
seen = {json.loads(l)["repo"] for l in open(os.path.join(OUT, f"candidates-{LANG.lower()}.log"))} if os.path.exists(os.path.join(OUT, f"candidates-{LANG.lower()}.log")) else set()
for l in (open(os.path.join(OUT, f"candidates-{LANG.lower()}.jsonl")) if os.path.exists(os.path.join(OUT, f"candidates-{LANG.lower()}.jsonl")) else []):
    r = json.loads(l); per_repo[r["repo"]] = per_repo.get(r["repo"], 0) + 1
page = int(os.environ.get("START_PAGE", "1"))      # continuing a search: the next pages, same order
while found < WANT and page <= 20:                   # GitHub search returns at most 1,000 results (20 pages of 50)
    q = f"language:{LANG} stars:300..15000 archived:false fork:false pushed:>2025-09-01"
    res = api(f"/search/repositories?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page=50&page={page}"); page += 1
    time.sleep(2.5)
    if not res or not res.get("items"): break
    for repo in res["items"]:
        if found >= WANT: break
        full = repo["full_name"]; owner = full.split("/")[0].lower()
        if full in seen: continue
        lic = (repo.get("license") or {}).get("spdx_id")
        if owner in EXCL: L(full, "repo", "excluded owner"); continue
        if lic not in LIC: L(full, "repo", f"license {lic}"); continue
        if repo.get("size", 0) > 300_000: L(full, "repo", "size > 300 MB"); continue
        br = repo["default_branch"]
        wfs = api(f"/repos/{full}/actions/workflows?per_page=100") or {}
        wfs = [w for w in wfs.get("workflows", []) if w.get("state") == "active" and TESTY.search(w["name"] + " " + w["path"]) or (w.get("state") == "active" and re.search(r"\bci\b|go\.yml|python|main", w["name"] + w["path"], re.I))]
        if not wfs: L(full, "repo", "no test-like active workflow"); continue
        for wf in wfs[:3]:
            if per_repo.get(full, 0) >= 2 or found >= WANT: break
            runs = api(f"/repos/{full}/actions/workflows/{wf['id']}/runs?branch={urllib.parse.quote(br)}&event=push&per_page=100&created=%3E%3D{SINCE}") or {}
            rs = [r for r in runs.get("workflow_runs", []) if r.get("status") == "completed"]
            rs.sort(key=lambda r: r["created_at"])
            for a, b in zip(rs, rs[1:]):
                if per_repo.get(full, 0) >= 2 or found >= WANT: break
                if not (a["conclusion"] == "failure" and b["conclusion"] == "success"): continue
                item = f"{a['head_sha'][:12]}->{b['head_sha'][:12]} ({wf['name']})"
                fix = api(f"/repos/{full}/commits/{b['head_sha']}")
                if not fix: L(full, item, "fix commit not readable"); continue
                if [p["sha"] for p in fix.get("parents", [])] != [a["head_sha"]]: L(full, item, "next green run is not the immediate child commit"); continue
                files = fix.get("files", [])
                names = [f["filename"] for f in files]; churn = sum(f.get("changes", 0) for f in files)
                src = [n for n in names if not TESTFILE.search(n) and not ENVFILE.search(n) and not n.lower().endswith((".md", ".rst", ".txt"))]
                if not src: L(full, item, "fix touches no non-test source file", files=names[:10]); continue
                if len(names) > 10 or churn > 300: L(full, item, f"fix too large ({len(names)} files, {churn} lines)"); continue
                jobs = api(f"/repos/{full}/actions/runs/{a['id']}/jobs?per_page=100") or {}
                failed = [j for j in jobs.get("jobs", []) if j.get("conclusion") == "failure"]
                if not failed: L(full, item, "no failed job listed"); continue
                j = failed[0]; fstep = next((s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"), "")
                if not (TESTY.search(j["name"]) or TESTY.search(fstep)) or NOT_TEST_STEP.search(fstep): L(full, item, f"failed step is not a test step: job '{j['name']}' step '{fstep}'"); continue
                logtxt = job_log(full, j["id"])
                if not logtxt: L(full, item, "job log not available (expired or deleted)"); continue
                ft = failing_tests(logtxt[-400_000:])
                if LANG == "Go" and not (ft["go_pkgs"] or ft["go_tests"]): L(full, item, "no Go test failure in the job log"); continue
                if LANG == "Python" and not ft["py_tests"]: L(full, item, "no pytest FAILED line in the job log"); continue
                hidden = [n for n in names if TESTFILE.search(n)]
                rec = {"repo": full, "language": LANG, "stars": repo["stargazers_count"], "license": lic, "default_branch": br,
                       "workflow": wf["name"], "workflow_path": wf["path"], "broken_sha": a["head_sha"], "fix_sha": b["head_sha"],
                       "failed_run": a["html_url"], "fixed_run": b["html_url"], "failed_job": j["name"], "failed_step": fstep,
                       "fix_files": names, "fix_churn": churn, "hidden_test_files": hidden, **ft}
                keep.write(json.dumps(rec) + "\n"); keep.flush()
                L(full, item, "candidate", failed_job=j["name"], failed_step=fstep)
                per_repo[full] = per_repo.get(full, 0) + 1; found += 1
                print(f"[{found}/{WANT}] {full} {a['head_sha'][:10]}->{b['head_sha'][:10]} {j['name']} | {len(hidden)} hidden test files | calls {calls}", flush=True)
print(f"done: {found} candidates, {calls} API calls", flush=True)
