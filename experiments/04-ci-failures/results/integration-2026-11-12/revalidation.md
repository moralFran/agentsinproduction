# Re-validation of the archived agent patches with the hardened validator (cluster, 2026-11-12)

What the new validator (`cases/validate.py`: three fresh suite pods, then three fresh hidden-test pods) says about each archived
patch, next to the outcome the archived executor recorded. **This is not a re-classification**: the archived outcomes stand on the
harness that produced them. The archived executor ran the suite 3 times and the hidden tests once in ONE pod; the new one runs
each sample in its own pod. Byte-identical patches of a case were validated once (column *same patch as*).

- Attempts in the archive: 66; with an empty patch (not validated, nothing to apply): 10; non-empty: 56.
- Distinct patches: 36. Re-validated: 56 attempts (36 distinct patches); not run: 0.
- **Same outcome: 50 of 56. Different: 6.**

## Differences

| Run | Case | Archived | New validator | Suite | Hidden | Reason given |
|---|---|---|---|---|---|---|
| v1-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |
| v1-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |
| v1-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |
| v2-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |
| v2-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |
| v2-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests; the archived run had none |

nkanaev/yarr: the maintainer's fix is only a test fixture (`src/parser/fixtures/atom/link-in-id.xml`). The archived preparation did not treat
`fixtures/` as test data, so the case had no hidden tests (README, tool note of 12/11; amendment 24 of `criteria.md`, which already
keeps yarr out of the main analysis). The current `cases/prep.py` does, so the fixture change is now the hidden test: the six patches
pass the original suite 3/3 and fail it 0/3 once the maintainer's fixture is in place. Reproduction control for the case: maintainer's
fix 3/3 pass, broken code plus the fixture 3/3 pass (`discriminates` false: the fixture is the fix).

## Outcome counts (re-validated attempts)

| Outcome | Archived | New validator |
|---|---|---|
| ci_still_red | 13 | 13 |
| green_fails_hidden | 11 | 17 |
| green_no_hidden_tests | 18 | 12 |
| green_passes_hidden | 14 | 14 |

## Published numbers, recomputed with the new validator's outcomes (arithmetic only)

Main analysis = 8 cases x 3 repetitions x 2 versions. "Green" = suite 3/3 and accepted by the validator (any of the three green outcomes).
Attempts with an empty patch keep their archived outcome (`no_patch`: not green in either column).

| Number | Published (archive) | What the new validator says |
|---|---|---|
| Main-analysis attempts | 48 | 48 |
| Green | 30 | 30 |
| Green that failed the maintainer's hidden tests | 4 | 4 |
| ... of those, gobwas/ws | 4 | 4 |
| v1 green | 15 | 15 |
| v2 green | 15 | 15 |

All main-analysis patches were re-validated.

## One row per attempt

| Run | Case | Archived outcome | New outcome | Suite passes of 3 | Hidden passes of 3 | Same? | Same patch as |
|---|---|---|---|---|---|---|---|
| v1-e88f0806-r1 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v1-e88f0806-r2 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v1-e88f0806-r3 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v2-e88f0806-r1 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v2-e88f0806-r2 | gobwas-ws-a567dfd6 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | - |
| v2-e88f0806-r3 | gobwas-ws-a567dfd6 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | - |
| v1-c2452a82-r1 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-c2452a82-r3 v2-c2452a82-r1 v2-c2452a82-r2 v2-c2452a82-r3 |
| v1-c2452a82-r2 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | - |
| v1-c2452a82-r3 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-c2452a82-r1 v2-c2452a82-r1 v2-c2452a82-r2 v2-c2452a82-r3 |
| v2-c2452a82-r1 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-c2452a82-r1 v1-c2452a82-r3 v2-c2452a82-r2 v2-c2452a82-r3 |
| v2-c2452a82-r2 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-c2452a82-r1 v1-c2452a82-r3 v2-c2452a82-r1 v2-c2452a82-r3 |
| v2-c2452a82-r3 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-c2452a82-r1 v1-c2452a82-r3 v2-c2452a82-r1 v2-c2452a82-r2 |
| v1-69bc3125-r1 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r2 v1-69bc3125-r3 v2-69bc3125-r1 v2-69bc3125-r2 v2-69bc3125-r3 |
| v1-69bc3125-r2 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r1 v1-69bc3125-r3 v2-69bc3125-r1 v2-69bc3125-r2 v2-69bc3125-r3 |
| v1-69bc3125-r3 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r1 v1-69bc3125-r2 v2-69bc3125-r1 v2-69bc3125-r2 v2-69bc3125-r3 |
| v2-69bc3125-r1 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r1 v1-69bc3125-r2 v1-69bc3125-r3 v2-69bc3125-r2 v2-69bc3125-r3 |
| v2-69bc3125-r2 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r1 v1-69bc3125-r2 v1-69bc3125-r3 v2-69bc3125-r1 v2-69bc3125-r3 |
| v2-69bc3125-r3 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | v1-69bc3125-r1 v1-69bc3125-r2 v1-69bc3125-r3 v2-69bc3125-r1 v2-69bc3125-r2 |
| v1-bbbe6833-r1 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | v1-bbbe6833-r3 v2-bbbe6833-r1 v2-bbbe6833-r2 v2-bbbe6833-r3 |
| v1-bbbe6833-r2 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | - |
| v1-bbbe6833-r3 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | v1-bbbe6833-r1 v2-bbbe6833-r1 v2-bbbe6833-r2 v2-bbbe6833-r3 |
| v2-bbbe6833-r1 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | v1-bbbe6833-r1 v1-bbbe6833-r3 v2-bbbe6833-r2 v2-bbbe6833-r3 |
| v2-bbbe6833-r2 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | v1-bbbe6833-r1 v1-bbbe6833-r3 v2-bbbe6833-r1 v2-bbbe6833-r3 |
| v2-bbbe6833-r3 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | 0/3 | - | same | v1-bbbe6833-r1 v1-bbbe6833-r3 v2-bbbe6833-r1 v2-bbbe6833-r2 |
| v1-56d24d7d-r1 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r2 v1-56d24d7d-r3 v2-56d24d7d-r1 v2-56d24d7d-r2 v2-56d24d7d-r3 |
| v1-56d24d7d-r2 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r1 v1-56d24d7d-r3 v2-56d24d7d-r1 v2-56d24d7d-r2 v2-56d24d7d-r3 |
| v1-56d24d7d-r3 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r1 v1-56d24d7d-r2 v2-56d24d7d-r1 v2-56d24d7d-r2 v2-56d24d7d-r3 |
| v2-56d24d7d-r1 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r1 v1-56d24d7d-r2 v1-56d24d7d-r3 v2-56d24d7d-r2 v2-56d24d7d-r3 |
| v2-56d24d7d-r2 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r1 v1-56d24d7d-r2 v1-56d24d7d-r3 v2-56d24d7d-r1 v2-56d24d7d-r3 |
| v2-56d24d7d-r3 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | 0/3 | - | same | v1-56d24d7d-r1 v1-56d24d7d-r2 v1-56d24d7d-r3 v2-56d24d7d-r1 v2-56d24d7d-r2 |
| v1-1899ffc2-r1 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v1-1899ffc2-r2 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v1-1899ffc2-r3 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v2-1899ffc2-r1 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v2-1899ffc2-r2 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v2-1899ffc2-r3 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v1-eb82db29-r1 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | v1-eb82db29-r2 v2-eb82db29-r1 |
| v1-eb82db29-r2 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | v1-eb82db29-r1 v2-eb82db29-r1 |
| v1-eb82db29-r3 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v2-eb82db29-r1 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | v1-eb82db29-r1 v1-eb82db29-r2 |
| v2-eb82db29-r2 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v2-eb82db29-r3 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | - |
| v1-1206f641-r3 | rmax-scrapy-redis-8d8672f2 | ci_still_red | ci_still_red | 0/3 | - | same | - |
| v1-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v1-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v1-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v2-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v2-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v2-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | - |
| v2-d735ebc1-r3 | boyter-scc-4288f7c8 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v1-a352a7c0-r1 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v1-a352a7c0-r2 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v1-a352a7c0-r3 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v2-a352a7c0-r1 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v2-a352a7c0-r2 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |
| v2-a352a7c0-r3 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | - |

## Attempts with an empty patch (not validated)

v1-d735ebc1-r1 (boyter-scc), v1-1206f641-r1 (rmax-scrapy-redis), v1-d735ebc1-r2 (boyter-scc), v1-1206f641-r2 (rmax-scrapy-redis), v1-d735ebc1-r3 (boyter-scc), v2-d735ebc1-r1 (boyter-scc), v2-1206f641-r1 (rmax-scrapy-redis), v2-d735ebc1-r2 (boyter-scc), v2-1206f641-r2 (rmax-scrapy-redis), v2-1206f641-r3 (rmax-scrapy-redis)
