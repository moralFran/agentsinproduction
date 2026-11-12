# Reproduction of the 11 frozen cases on the fresh cluster (2026-11-12) vs the archive

New preparation (per-case pods in `ci-prep`, private fixed-tree Go cache) and new controls (`hidden_control`, `integrity_control`).
Archive: all 11 `reproduced` (broken 3/3 fail, fixed 3/3 pass; the archived harness had no hidden or integrity control).
`hidden_control`: the maintainer's test changes on the fixed tree (3 runs) and on the broken tree plus only those test changes (3 runs);
`discriminates` = all fixed runs pass and all broken-plus-tests runs fail. Nothing was excluded or fixed on the basis of this table.

| Case | Archived verdict | New verdict | Broken failed | Fixed passed | Hidden on fixed (3) | Hidden on broken + tests (3) | discriminates | integrity_control | Same verdict? |
|---|---|---|---|---|---|---|---|---|---|
| openbyteinc-quantdinger-733f7bc7 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| ludwig-ai-ludwig-6a122a8e | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | no hidden tests | no hidden tests | n/a (false) | clean | same |
| mark3labs-mcp-go-1969a6b9 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| boyter-scc-4288f7c8 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | pass/pass/pass | False | clean | same |
| gobwas-ws-a567dfd6 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| sigstore-cosign-1ab7015b | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| pyinfra-dev-pyinfra-e7e42b68 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | no hidden tests | no hidden tests | n/a (false) | clean | same |
| rmax-scrapy-redis-8d8672f2 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| tdewolff-minify-fa882446 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |
| nkanaev-yarr-957e81dd | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass (archive: no hidden tests for this case) | pass/pass/pass | False | clean | same |
| alicebob-miniredis-ce093519 | reproduced (3/3 fail, 3/3 pass) | **reproduced** | 3/3 | 3/3 | pass/pass/pass | fail/fail/fail | True | clean | same |

**Same verdict as the archive: 11 of 11.**

## Timing of the first run in a fresh pod (seconds; Go compiles from an empty build cache)

| Case | Archive: broken runs | New: broken runs | New: fixed runs |
|---|---|---|---|
| openbyteinc-quantdinger-733f7bc7 | 9.3, 8.6, 7.8 | 10.5, 10.5, 10.3 | 10.6, 8.4, 10.3 |
| ludwig-ai-ludwig-6a122a8e | 168.4, 168.2, 158.4 | 217.6, 184.2, 181.5 | 191.5, 188.6, 145.9 |
| mark3labs-mcp-go-1969a6b9 | 117.0, 22.8, 23.4 | 102.4, 21.7, 22.5 | 109.0, 20.6, 20.7 |
| boyter-scc-4288f7c8 | 120.5, 34.9, 37.5 | 127.6, 37.8, 34.6 | 118.4, 35.4, 29.9 |
| gobwas-ws-a567dfd6 | 68.3, 4.8, 3.4 | 66.8, 3.0, 3.7 | 62.1, 2.9, 3.3 |
| sigstore-cosign-1ab7015b | 285.2, 137.5, 147.0 | 255.3, 138.5, 124.3 | 335.8, 138.1, 148.6 |
| pyinfra-dev-pyinfra-e7e42b68 | 6.2, 5.9, 5.3 | 7.6, 7.1, 6.6 | 7.4, 7.2, 6.2 |
| rmax-scrapy-redis-8d8672f2 | 5.2, 3.7, 3.5 | 6.6, 6.4, 6.1 | 5.0, 4.6, 4.9 |
| tdewolff-minify-fa882446 | 129.9, 6.7, 5.7 | 55.0, 2.7, 2.3 | 50.3, 3.1, 2.3 |
| nkanaev-yarr-957e81dd | 94.1, 7.6, 6.0 | 59.9, 2.7, 3.0 | 44.3, 1.7, 1.7 |
| alicebob-miniredis-ce093519 | 71.3, 5.5, 5.0 | 59.7, 5.6, 5.4 | 74.0, 5.3, 4.9 |
