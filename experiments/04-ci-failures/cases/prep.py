#!/usr/bin/env python3
"""Preparation of one candidate case, WITH network (runs on aip-ci-01 inside the box image, never on the Mac).
  - clone the repository, check out the broken commit;
  - the maintainer's fix and its test-file part (the hidden tests) go to /srv/ci/secret/<id>/ (never mounted for the agent);
  - snapshot = the broken tree with NO history (fresh git repo, one commit, no remotes) in /srv/ci/cases/<id>/snapshot;
  - dependencies prepared so the case runs offline: Go module cache (and toolchain) in .../gomod; Python venv in .../venv,
    with the project installed in editable mode at the path the pods use for the working copy (.../repo);
  - the test command of the case (criteria.md §11) in .../meta.json.
usage: prep.py '<candidate json line>'"""
import json, os, re, shutil, subprocess, sys, pathlib

c = json.loads(sys.argv[1])
cid = re.sub(r"[^a-z0-9]+", "-", c["repo"].lower()).strip("-")[:40] + "-" + c["broken_sha"][:8]
ROOT = pathlib.Path("/srv/ci"); case = ROOT / "cases" / cid; secret = ROOT / "secret" / cid; work = ROOT / "work" / cid
for d in (case, secret, work):
    subprocess.run(["chmod", "-R", "u+w", str(d)], capture_output=True)      # Go makes its module cache read-only
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
# test files, including test EXPECTATIONS: snapshot files (__snapshots__/, *.snap) and golden files (*.golden, golden/).
# The first version missed snapshots; found by the smoke test on 11/11 (google/osv-scanner: fix and patch were only a .snap)
TESTFILE = re.compile(r"(^|/)(tests?|testdata|testing|__snapshots__|golden|fixtures)(/|$)|_test\.go$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|\.snap$|\.golden$")   # fixtures/ added 12/11 (audit; future runs only)
LOG = open(secret / "prep.log", "w")       # the log shows the fix diff: it stays with the secret files, never in the case dir

def sh(cmd, cwd=None, env=None, check=True, timeout=1800):
    LOG.write(f"$ {cmd}\n"); LOG.flush()
    p = subprocess.run(cmd, shell=True, cwd=cwd, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    LOG.write(p.stdout[-20000:] + f"[rc {p.returncode}]\n"); LOG.flush()
    if check and p.returncode: raise SystemExit(f"PREP_FAIL {cid}: {cmd} -> rc {p.returncode}: {p.stdout[-300:]}")
    return p

def fail(why): print(json.dumps({"id": cid, "prep": "fail", "why": why})); sys.exit(0)

clone = work / "clone"
sh(f"git clone -q --filter=blob:none https://github.com/{c['repo']}.git {clone}", timeout=1200)
sh(f"git checkout -q {c['broken_sha']}", cwd=clone)
sh(f"git cat-file -e {c['fix_sha']}", cwd=clone)
(secret / "fix.diff").write_text(sh(f"git diff --binary {c['broken_sha']} {c['fix_sha']}", cwd=clone).stdout)
hidden = [f for f in c["fix_files"] if TESTFILE.search(f)]
(secret / "hidden.diff").write_text(sh(f"git diff --binary {c['broken_sha']} {c['fix_sha']} -- " + " ".join(hidden), cwd=clone).stdout if hidden else "")
(secret / "fix.json").write_text(json.dumps({"fix_sha": c["fix_sha"], "fix_files": c["fix_files"], "hidden_files": hidden}))
snap = case / "snapshot"
sh(f"rsync -a --exclude .git {clone}/ {snap}/")
sh("git init -q && git add -A && git -c user.name=snapshot -c user.email=snapshot@example.invalid commit -q -m snapshot", cwd=snap)
# meta.json is visible to the agent: nothing about the fix in it (no fix sha, no hidden test names or command)
meta = {"id": cid, "repo": c["repo"], "language": c["language"], "broken_sha": c["broken_sha"], "workflow": c["workflow"], "failed_job": c["failed_job"]}
smeta = {"fix_sha": c["fix_sha"], "failed_run": c["failed_run"], "fixed_run": c["fixed_run"], "hidden_files": hidden}
repo = case / "repo"                       # the path of the working copy inside the pods; prepared here once for installs
sh(f"rsync -a {snap}/ {repo}/")

if c["language"] == "Go":
    pkgs = c["go_pkgs"]
    mods = {}
    for gm in sorted(repo.rglob("go.mod")):
        if "/vendor/" in str(gm) or "/testdata/" in str(gm): continue
        m = re.search(r"^module\s+(\S+)", gm.read_text(), re.M)
        if m: mods[m.group(1)] = gm.parent.relative_to(repo)
    if not mods: fail("no go.mod")
    if pkgs:
        best = max((mp for mp in mods if any(p == mp or p.startswith(mp + "/") for p in pkgs)), key=len, default=None)
        if not best: fail(f"failing packages outside every module: {pkgs[:3]}")
        pkgs = [p for p in pkgs if p == best or p.startswith(best + "/")]
        wd = mods[best]; target = " ".join(pkgs)
    else:
        wd = mods[min(mods, key=len)]; target = "./..."
    gomod = case / "gomod"
    env = {"GOMODCACHE": str(gomod), "GOTOOLCHAIN": "auto", "GOFLAGS": "-mod=mod", "GOCACHE": str(work / "gocache"), "GOPATH": str(work / "gopath")}
    sh("go version", cwd=repo / wd, env=env)
    sh("go mod download", cwd=repo / wd, env=env, check=False)
    sh(f"go test -count=1 -run '^$' {target}", cwd=repo / wd, env=env, check=False)          # fetches everything the build needs
    fx = work / "fixed"; sh(f"rsync -a {repo}/ {fx}/"); sh(f"git apply --binary {secret/'fix.diff'}", cwd=fx)
    sh(f"go test -count=1 -run '^$' {target}", cwd=fx / wd, env=env, check=False)
    def pkg_of(h):
        """The package a hidden file belongs to: its own directory, or for test data the nearest directory above with Go files."""
        d = (repo / h).parent
        while d != repo and not any(d.glob("*.go")): d = d.parent
        try: return "./" + str(d.relative_to(repo / wd))
        except ValueError: return None
    hidden_pkgs = sorted({pkg_of(h) for h in hidden} - {None})
    meta.update(workdir=str(wd), test_cmd=f"go test -count=1 {target}", go_version=sh("go version", cwd=repo / wd, env=env).stdout.strip().split()[-2])
    smeta["hidden_cmd"] = f"go test -count=1 {' '.join(sorted(set(target.split()) | set(hidden_pkgs)))}" if hidden else ""   # any maintainer change to tests or test data triggers the hidden run (12/11)
    sh(f"chmod -R a+rX {gomod}", check=False)          # a dangling symlink in a module must not fail the case
else:
    ver = (c.get("py_version") or "3.12").rsplit(".", 1)[0] if c.get("py_version", "").count(".") == 2 else (c.get("py_version") or "3.12")
    files = sorted({t.split("::")[0] for t in c["py_tests"]})
    found = []
    for f in files:
        if (repo / f).exists(): found.append(f); continue
        # CI logs may print paths relative to another directory or absolute on the runner ("../../project/tests/x.py",
        # "/Users/runner/work/repo/repo/tests/x.py"): match by the longest tail of path components that is unique here
        parts = [x for x in pathlib.PurePosixPath(f).parts if x not in ("..", ".", "/")]
        cands = [q for q in repo.rglob(parts[-1]) if ".git" not in q.parts] if parts else []
        for k in range(len(parts), 0, -1):
            hits = [q for q in cands if q.relative_to(repo).parts[-k:] == tuple(parts[-k:])]
            if len(hits) == 1: found.append(str(hits[0].relative_to(repo))); break
            if len(hits) > 1: break
    if not found: fail(f"failing test files not found in the tree: {files[:3]}")
    # the project the failing tests belong to: nearest directory upwards with pyproject.toml / setup.py / setup.cfg /
    # requirements.txt (a repo may keep its Python project in a subfolder, e.g. backend/)
    def proj(f):
        d = (repo / f).parent
        while True:
            if any((d / m).exists() for m in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")) or d == repo: return d
            d = d.parent
    P = max({proj(f) for f in found}, key=lambda d: sum(proj(f) == d for f in found))
    wd = P.relative_to(repo); rel = [str((repo / f).relative_to(P)) for f in found if (repo / f).is_relative_to(P)]
    uvenv = {"UV_PYTHON_INSTALL_DIR": "/srv/ci/uv/python", "UV_CACHE_DIR": str(work / "uvcache"), "UV_LINK_MODE": "copy"}
    venv = case / "venv"
    sh(f"uv venv -q --python {ver} {venv}", env=uvenv)
    pip = f"uv pip install -q --python {venv}/bin/python"
    reqs = [str(q.relative_to(P)) for pat in ("requirements.txt", "requirements*dev*.txt", "requirements*test*.txt", "dev-requirements.txt", "test-requirements.txt",
            "requirements/base*.txt", "requirements/test*.txt", "requirements/dev*.txt", "tests/requirements*.txt") for q in P.glob(pat)]
    rok = [sh(f"{pip} -r {r}", cwd=P, env=uvenv, check=False).returncode == 0 for r in reqs]
    ok = False
    if any((P / m).exists() for m in ("pyproject.toml", "setup.py", "setup.cfg")):
        ok = sh(f'{pip} -e ".[test,tests,testing,dev]"', cwd=P, env=uvenv, check=False).returncode == 0
        if not ok: ok = sh(f"{pip} -e .", cwd=P, env=uvenv, check=False).returncode == 0
        for g in ("test", "tests", "dev"):
            sh(f"{pip} --group {g} -e .", cwd=P, env=uvenv, check=False)
    sh(f"{pip} pytest", cwd=P, env=uvenv, check=False)
    if not ok and not any(rok): fail("project could not be installed")
    hidden_py = [str((repo / h).relative_to(P)) for h in hidden if re.search(r"(^|/)test_[^/]*\.py$|_test\.py$", h) and (repo / h).is_relative_to(P)]
    meta.update(workdir=str(wd), python=ver, test_cmd="python -m pytest -q -p no:cacheprovider " + " ".join(rel))
    smeta["hidden_cmd"] = ("python -m pytest -q -p no:cacheprovider " + " ".join(sorted(set(rel) | set(hidden_py)))) if hidden else ""   # also when only test data changed (12/11)
    sh(f"chmod -R a+rX {venv} /srv/ci/uv", check=False)
# build products of the preparation (e.g. compiled C extensions of an editable install) are not in the snapshot: keep them
# as an overlay that the pods copy over the working copy and exclude from git, so they never show up in a patch
over = case / "overlay"; listed = []
for f in repo.rglob("*"):
    rel = f.relative_to(repo)
    if rel.parts and rel.parts[0] == ".git" or f.is_dir() or (snap / rel).exists(): continue
    (over / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, over / rel, follow_symlinks=False); listed.append(str(rel))
(case / "overlay.list").write_text("".join("/" + x + "\n" for x in sorted(listed)))
meta["overlay_files"] = len(listed)
(case / "meta.json").write_text(json.dumps(meta, indent=1)); (secret / "meta.json").write_text(json.dumps({**meta, **smeta}, indent=1))
shutil.rmtree(work, ignore_errors=True)
print(json.dumps({"id": cid, "prep": "ok", "test_cmd": meta["test_cmd"], "hidden_cmd": smeta["hidden_cmd"]}))
