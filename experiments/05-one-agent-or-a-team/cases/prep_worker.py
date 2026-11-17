#!/usr/bin/env python3
"""Dependency stage of experiment 05, inside a disposable Kata pod in ci-prep (public HTTP(S) and DNS only; no secret
directory, no other task, no credentials). /input is the task snapshot, read-only. This is the ONLY place where
dependencies are fetched (criteria E6); every later pod runs without network.

  pub   `flutter pub get` in a copy of the snapshot, PUB_CACHE=/srv/ci/deps/pub-cache (shared, becomes read-only for
        the test and agent pods). The first task of a dependency set resolves freely and its pubspec.lock is stored in
        /srv/ci/deps/locks/<set>/; every other task of the set gets that lock and runs with --enforce-lockfile, so all
        tasks of a set (and all attempts) use one resolution.
  npm   `npm ci` in lib/internal/firebase (npm workspaces root), then `npm ci` in functions/, as the repository's CI
        does. node_modules are published once per lock set to /srv/ci/deps/node/<set>/{root,functions}.
Output for the controller: /output/overlay (files the resolution created in the working copy, without node_modules)
and /output/overlay.list (Git exclude patterns for them). Prints PREP_STEP <json> per step and PREP_WORKER_DONE."""
import json, os, pathlib, shutil, subprocess, time

FB = "lib/internal/firebase"


def run(args, cwd, check=True, env=None):
    t = time.monotonic()
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    print(f"$ {' '.join(args)}  (rc={p.returncode}, {time.monotonic() - t:.0f}s)\n{p.stdout[-6000:]}", flush=True)
    if check and p.returncode: raise SystemExit(f"required step failed: {' '.join(args)}")
    return p


def step(name, **kw): print("PREP_STEP " + json.dumps({"step": name, **kw}), flush=True)


def main():
    case = pathlib.Path("/srv/ci/cases") / os.environ["CASE_ID"]; repo = case / "repo"
    steps = os.environ["PREP_STEPS"].split(","); deps = pathlib.Path("/srv/ci/deps")
    subprocess.run(["rsync", "-rl", "--no-perms", "--chmod=u+rwX", "--omit-dir-times", "/input/", str(repo) + "/"], check=True)
    run(["flutter", "--version"], repo); run(["node", "--version"], repo); run(["npm", "--version"], repo)
    extra = set()                                            # files this worker adds that must not reach the overlay
    if "pub" in steps:
        lockdir = deps / "locks" / os.environ["PUB_SET"]; lock = lockdir / "pubspec.lock"
        if lock.exists():
            shutil.copyfile(lock, repo / "pubspec.lock")
            run(["flutter", "pub", "get", "--enforce-lockfile"], repo)
            same = (repo / "pubspec.lock").read_bytes() == lock.read_bytes()
            step("pub", mode="enforce-lockfile", set=os.environ["PUB_SET"], lock_unchanged=same)
            if not same: raise SystemExit("pubspec.lock changed under --enforce-lockfile")
        else:
            pins = json.loads(os.environ.get("PUB_PINS") or "{}")
            run(["flutter", "pub", "get"], repo)
            lockdir.mkdir(parents=True, exist_ok=True)
            if pins:
                # Exact pins for packages whose newest version does not compile with the parent tree (see
                # infra/locks/README.md for the evidence of each). The unpinned lock is kept for the record; the pins
                # are applied through a temporary pubspec_overrides.yaml in this copy only, and the resulting lock must
                # then satisfy the app's untouched pubspec.yaml on its own (--enforce-lockfile, overrides file removed).
                shutil.copyfile(repo / "pubspec.lock", lockdir / "pubspec.lock.unpinned")
                ov = repo / "pubspec_overrides.yaml"
                if ov.exists(): raise SystemExit("the tree already has a pubspec_overrides.yaml")
                tracked = (repo / "pubspec.yaml").read_text()
                # keep the app's own overrides (the vendored path dependency): pubspec_overrides.yaml replaces that section
                base = tracked[tracked.index("\ndependency_overrides:"):] if "\ndependency_overrides:" in tracked else "\ndependency_overrides:\n"
                section = base.split("\n\n")[0] if "\n\n" in base else base
                import re
                m = re.match(r"\ndependency_overrides:\n((?:[ \t]+.*\n|\s*#.*\n|\n(?=[ \t]))*)", base)
                body = m.group(1) if m else ""
                ov.write_text("dependency_overrides:\n" + body.rstrip("\n") + "\n" + "".join(f"  {k}: {v}\n" for k, v in sorted(pins.items())))
                print("pubspec_overrides.yaml (temporary):\n" + ov.read_text(), flush=True)
                run(["flutter", "pub", "get"], repo)
                ov.unlink()
                run(["flutter", "pub", "get", "--enforce-lockfile"], repo)
            shutil.copyfile(repo / "pubspec.lock", lock)
            step("pub", mode="resolved", set=os.environ["PUB_SET"], pins=pins)
        # the offline proof of this tree: the same command must succeed again without the network being asked
        p = run(["flutter", "pub", "get", "--offline", "--enforce-lockfile"], repo, check=False)
        step("pub-offline-check", rc=p.returncode)
    if "npm" in steps:
        out = deps / "node" / os.environ["NODE_SET"]
        if out.exists(): shutil.rmtree(out)
        root = repo / FB; stub = root / "admin-scripts" / "package.json"; used_stub = False
        p = run(["npm", "ci", "--no-audit", "--no-fund"], root, check=False)
        if p.returncode and not stub.exists():
            # The root package.json lists the workspace "admin-scripts", whose package.json is not tracked (the directory
            # is mostly git-ignored). Minimal handling: a manifest rebuilt from the lock's own "admin-scripts" entry,
            # in this preparation copy only. It is not added to the snapshot or to the overlay.
            entry = json.load(open(root / "package-lock.json"))["packages"].get("admin-scripts", {})
            manifest = {k: entry[k] for k in ("name", "version", "dependencies", "devDependencies", "optionalDependencies", "peerDependencies", "engines") if k in entry}
            manifest.setdefault("name", "admin-scripts"); manifest["private"] = True
            stub.parent.mkdir(parents=True, exist_ok=True); stub.write_text(json.dumps(manifest, indent=2) + "\n"); used_stub = True
            extra.add(str(stub.relative_to(repo)))
            p = run(["npm", "ci", "--no-audit", "--no-fund"], root, check=True)
        elif p.returncode: raise SystemExit("npm ci failed in the workspace root")
        step("npm-root", admin_scripts_stub=used_stub)
        p2 = run(["npm", "ci", "--no-audit", "--no-fund"], root / "functions", check=False)
        step("npm-functions", rc=p2.returncode)
        if p2.returncode: raise SystemExit("npm ci failed in functions/")
        # Published as <set>/node_modules and <set>/functions/node_modules: the same relative layout npm wrote, so that
        # Node's upward lookup from the nested set still finds the hoisted one when both are reached through symlinks.
        (out / "node_modules").mkdir(parents=True)
        subprocess.run(["rsync", "-a", "--no-owner", "--no-group", str(root / "node_modules") + "/", str(out / "node_modules") + "/"], check=True)
        fn = root / "functions" / "node_modules"
        if fn.is_dir() and any(fn.iterdir()):
            (out / "functions" / "node_modules").mkdir(parents=True)
            subprocess.run(["rsync", "-a", "--no-owner", "--no-group", str(fn) + "/", str(out / "functions" / "node_modules") + "/"], check=True)
        ls = run(["npm", "ls", "--all", "--json"], root, check=False)
        (out / "npm-ls.json").write_text(ls.stdout)
        tops = run(["npm", "ls", "jest", "firebase-admin", "firebase-functions", "firebase-functions-test", "@firebase/rules-unit-testing"], root, check=False)
        (out / "DONE").write_text(json.dumps({"admin_scripts_stub": used_stub, "functions_node_modules": (out / "functions" / "node_modules").is_dir()}))
        step("npm-published", set=os.environ["NODE_SET"], functions_dir=(out / "functions" / "node_modules").is_dir())
    overlay = pathlib.Path("/output/overlay"); listed = []
    for directory, dirs, files in os.walk(repo):
        d = pathlib.Path(directory); r = d.relative_to(repo)
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules")]
        for f in files:
            rel = r / f
            if str(rel) in extra or (pathlib.Path("/input") / rel).exists(): continue
            (overlay / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(d / f, overlay / rel, follow_symlinks=False); listed.append(str(rel))
    overlay.mkdir(parents=True, exist_ok=True)
    def pattern(path):
        # the shallowest directory the snapshot does not have (e.g. /.dart_tool/), else the file itself: a generated
        # file inside a tracked directory must never turn that whole directory into an ignored one
        parts = path.split("/")
        for i in range(1, len(parts)):
            if not (pathlib.Path("/input") / "/".join(parts[:i])).exists(): return "/" + "/".join(parts[:i]) + "/"
        return "/" + path
    tops = sorted({pattern(p) for p in listed})
    pathlib.Path("/output/overlay.list").write_text("".join(t + "\n" for t in tops) + "node_modules\n")
    step("overlay", files=len(listed), top=tops)
    print("PREP_WORKER_DONE", flush=True)


if __name__ == "__main__": main()
