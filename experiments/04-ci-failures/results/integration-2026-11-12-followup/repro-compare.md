# Reproduction of the 11 frozen cases, follow-up round (2026-11-12), next to the archive and the first round

Harness: commit d5e1195 (preparation and `repro.sh` as in dec7c18), executor e7858e9 **plus the VM-only `safe.directory` fix** (`harness-fix/`).
New in this round: the checkout is restored before every sample; `prep_control.broken_compiles` (Go, from preparation); `cache_control` (Go: the
maintainer's fix run 3 + 3 times with the agent's, broken-tree, module cache); the integrity check also fingerprints `.git/index`, `.git/config`,
`.git/info/exclude`, `.git/HEAD` and every `.gitignore`, and reports a change as `test_changed_tree`.

| Case | Archive | First round | This round | Broken failed | Fixed passed | Hidden on fixed | Hidden on broken + tests | hidden applicable / discriminates | integrity_control | broken_compiles | cache_control (applicable / passes / integrity; suite; hidden) | vs first round |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openbyteinc-quantdinger-733f7bc7 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | None | not applicable | same |
| ludwig-ai-ludwig-6a122a8e | reproduced | reproduced (discriminates False, integrity clean) | **reproduced** | 3/3 | 3/3 | no hidden tests | no hidden tests | False / False | clean | None | not applicable | same |
| mark3labs-mcp-go-1969a6b9 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| boyter-scc-4288f7c8 | reproduced | reproduced (discriminates False, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | pass/pass/pass | True / False | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| gobwas-ws-a567dfd6 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| sigstore-cosign-1ab7015b | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| pyinfra-dev-pyinfra-e7e42b68 | reproduced | reproduced (discriminates False, integrity clean) | **reproduced** | 3/3 | 3/3 | no hidden tests | no hidden tests | False / False | clean | None | not applicable | same |
| rmax-scrapy-redis-8d8672f2 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | None | not applicable | same |
| tdewolff-minify-fa882446 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| nkanaev-yarr-957e81dd | reproduced | reproduced (discriminates False, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | pass/pass/pass | True / False | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |
| alicebob-miniredis-ce093519 | reproduced | reproduced (discriminates True, integrity clean) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True / True | clean | True | yes / True / clean; pass/pass/pass; pass/pass/pass | same |

**Same verdict, `discriminates` and integrity outcome as the first round: 11 of 11.** All 11 were `reproduced` in the archive.

## Seconds per run (first run in a pod compiles from an empty build cache)

| Case | First round: fixed runs | This round: broken runs | This round: fixed runs | This round: fix with the agent's cache (suite) |
|---|---|---|---|---|
| openbyteinc-quantdinger-733f7bc7 | 10.6, 8.4, 10.3 | 9.1, 8.2, 8.3 | 7.1, 8.0, 7.5 |  |
| ludwig-ai-ludwig-6a122a8e | 191.5, 188.6, 145.9 | 143.4, 156.9, 148.0 | 183.9, 167.4, 144.4 |  |
| mark3labs-mcp-go-1969a6b9 | 109.0, 20.6, 20.7 | 75.3, 19.1, 19.0 | 92.1, 19.8, 20.3 | 94.7, 21.4, 21.4 |
| boyter-scc-4288f7c8 | 118.4, 35.4, 29.9 | 109.1, 32.1, 30.0 | 127.9, 33.9, 28.0 | 138.8, 34.8, 29.9 |
| gobwas-ws-a567dfd6 | 62.1, 2.9, 3.3 | 50.4, 2.9, 2.7 | 48.7, 2.3, 2.2 | 37.1, 1.9, 1.7 |
| sigstore-cosign-1ab7015b | 335.8, 138.1, 148.6 | 319.6, 135.6, 143.9 | 264.2, 143.6, 127.1 | 328.8, 134.3, 144.9 |
| pyinfra-dev-pyinfra-e7e42b68 | 7.4, 7.2, 6.2 | 5.8, 5.8, 6.1 | 6.7, 6.1, 6.1 |  |
| rmax-scrapy-redis-8d8672f2 | 5.0, 4.6, 4.9 | 6.0, 5.0, 5.1 | 4.9, 4.3, 4.4 |  |
| tdewolff-minify-fa882446 | 50.3, 3.1, 2.3 | 70.4, 3.9, 3.3 | 81.6, 4.6, 4.0 | 51.7, 2.3, 2.5 |
| nkanaev-yarr-957e81dd | 44.3, 1.7, 1.7 | 45.9, 2.0, 1.8 | 58.9, 4.4, 2.9 | 35.5, 2.1, 2.2 |
| alicebob-miniredis-ce093519 | 74.0, 5.3, 4.9 | 43.8, 3.6, 3.6 | 42.7, 3.5, 3.6 | 56.8, 4.7, 4.7 |
