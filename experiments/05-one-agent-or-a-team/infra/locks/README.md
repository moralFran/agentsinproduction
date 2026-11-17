# Dependency resolution of the lab (criteria E6) · 2026-11-15

> Written in English in the original, which is kept in the author's private production repository (the original calls
> itself private because it names the app's packages). Two edits for the public copy, both marked in square brackets:
> an app source file and an app commit are described instead of named. Nothing else was changed.

Private (package names of the app). The generated locks of each dependency set are in this folder; every task and
every attempt uses them through `flutter pub get --enforce-lockfile` at preparation time and no network afterwards.

## What is resolved, where
- `flutter pub get` and `npm ci` run only in a disposable Kata pod of `ci-prep` (`cases/prep_worker.py`), with the
  task snapshot read-only as input. Pub cache: `/srv/ci/deps/pub-cache` (one, shared). `node_modules`: one set per npm
  lock set under `/srv/ci/deps/node/<set>/`. Both are mounted read-only in agent and executor pods.
- Dependency sets are identified by content: the pubspec without its `version:` line (+ the vendored package's
  pubspec), and the four npm manifest/lock files.

## The pin (deviation from a plain resolution; proposed amendment to E6)
`pins.json` holds one exact pin: **`connectivity_plus_platform_interface` 2.0.1**.

Evidence that the plain resolution of 15/11 does not give the owner's environment back:
- With no pin the resolver picks 2.1.0. `flutter analyze lib test` on task 4's tree with the owner's fix applied
  reports exactly one error: [an app source file, line 415], a `switch` over `ConnectivityResult` that is
  no longer exhaustive (`ConnectivityResult.satellite`).
- 2.1.0 was published on 2026-03-30 (pub.dev API), months before the 8 task commits (2026-06-17 to 2026-08-06). The app
  handled the new value only on 2026-10-27 ([the app's commit that handled it, private]). So the owner's untracked
  `pubspec.lock` still held 2.0.1 while he wrote the 8 commits; a clean `flutter pub get` on those dates would have
  failed the same way.
- Effect, measured on a partial unpinned run of task 4's Flutter suite with the owner's fix: 13 of the first 28 test
  files did not compile (the run was stopped there; each failing file costs a compiler restart).
- With the pin, the analyzer error is gone and the lock still satisfies the app's untouched `pubspec.yaml`
  (`flutter pub get --enforce-lockfile` and `--offline --enforce-lockfile` both return 0).

How it is applied: the worker resolves once without pins (kept as `pubspec.lock.unpinned`), then writes a temporary
`pubspec_overrides.yaml` in its own copy (the app's existing override of the vendored `cloud_firestore` plus the
pins), resolves again, deletes the overrides file and runs `flutter pub get --enforce-lockfile` against the app's own
pubspec. Nothing is added to the snapshot. The only difference between the two locks is that package (version, hash,
and the label `direct overridden`, which pub writes and does not validate).

Not done, on purpose: a resolution "as of the commit date" (it would also pick 2.1.0) and a reconstruction of the
owner's old lock (it no longer exists; the working copy's lock was upgraded on 2026-10-26).

## Git dependencies without a pinned ref
`google_maps_webservice` and `shake` have `ref: HEAD` in the pubspec. The commits resolved on 15/11 are in
`git-dependencies.txt` and inside each lock (`resolved-ref`).

## npm
`npm ci` in the workspace root accepts the missing `admin-scripts/package.json` (the workspace is skipped); no stub
was needed. `npm ci` in `functions/` is workspace-aware: it reinstalls from the ROOT lock, so
`functions/package-lock.json` is not what gets installed (firebase-functions-test 3.4.1, as in the root lock).
Jest needs one more thing the tracked tree lacks: the directory `admin-scripts/dashboard` named as a root of one Jest
project. The overlay adds it empty.
