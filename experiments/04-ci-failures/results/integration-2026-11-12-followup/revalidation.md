# Re-validation of the archived agent patches, follow-up round (cluster, 2026-11-12)

Validator of the follow-up harness (`cases/validate.py`, executor of commit e7858e9/d5e1195 **plus the VM-only `safe.directory` fix**, see
`harness-fix/`): three fresh suite pods, then three fresh hidden-test pods, both phases with the broken-tree Go cache; the integrity check
fingerprints Git metadata, the index (after one refresh) and every `.gitignore`. **Not a re-classification**: the archived outcomes stand.

- Non-empty archived patches: 56 attempts; re-validated here: 56 (36 distinct patches); not run: 0; empty patches (not validated): 10.
- **Against the archive: 50 same, 6 different.**
- **Against the first integration round (outcome and both 3/3 counts): 56 same, 0 different.**
- Outcome `test_changed_tree`: 0 attempts. Infrastructure errors or timeouts: 0.

## Differences from the archive

| Run | Case | Archived | First round | This round | Suite | Hidden | Reason given |
|---|---|---|---|---|---|---|---|
| v1-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |
| v1-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |
| v1-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |
| v2-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |
| v2-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |
| v2-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden (3/3, 0/3) | green_fails_hidden | 3/3 | 0/3 | the current preparation gives this case hidden tests (fixtures/ counts as test data); the archived run had none |

## Differences from the first integration round

None.

## Outcome counts

| Outcome | Archived | First round | This round |
|---|---|---|---|
| ci_still_red | 13 | 13 | 13 |
| green_fails_hidden | 11 | 17 | 17 |
| green_no_hidden_tests | 18 | 12 | 12 |
| green_passes_hidden | 14 | 14 | 14 |

## Published numbers of the main analysis, recomputed (arithmetic only)

Main analysis = 8 cases x 3 repetitions x 2 versions. "Green" = any of the three green outcomes. Empty patches are not green in any column.

| Number | Published (archive) | First round | This round |
|---|---|---|---|
| Main-analysis attempts | 48 | 48 | 48 |
| Green | 30 | 30 | 30 |
| Green that failed the maintainer's hidden tests | 4 | 4 | 4 |
| ... of those, gobwas/ws | 4 | 4 | 4 |
| v1 green | 15 | 15 | 15 |
| v2 green | 15 | 15 | 15 |

All main-analysis patches were re-validated in this round.

## One row per attempt

| Run | Case | Archived | First round | This round | Suite of 3 | Hidden of 3 | vs archive | vs first round |
|---|---|---|---|---|---|---|---|---|
| v1-e88f0806-r1 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v1-e88f0806-r2 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v1-e88f0806-r3 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v2-e88f0806-r1 | gobwas-ws-a567dfd6 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v2-e88f0806-r2 | gobwas-ws-a567dfd6 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-e88f0806-r3 | gobwas-ws-a567dfd6 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-c2452a82-r1 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-c2452a82-r2 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-c2452a82-r3 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-c2452a82-r1 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-c2452a82-r2 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-c2452a82-r3 | sigstore-cosign-1ab7015b | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-69bc3125-r1 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-69bc3125-r2 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-69bc3125-r3 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-69bc3125-r1 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-69bc3125-r2 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v2-69bc3125-r3 | tdewolff-minify-fa882446 | green_passes_hidden | green_passes_hidden | green_passes_hidden | 3/3 | 3/3 | same | same |
| v1-bbbe6833-r1 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-bbbe6833-r2 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-bbbe6833-r3 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-bbbe6833-r1 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-bbbe6833-r2 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-bbbe6833-r3 | mark3labs-mcp-go-1969a6b9 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-56d24d7d-r1 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-56d24d7d-r2 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-56d24d7d-r3 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-56d24d7d-r1 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-56d24d7d-r2 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v2-56d24d7d-r3 | alicebob-miniredis-ce093519 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-1899ffc2-r1 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-1899ffc2-r2 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-1899ffc2-r3 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-1899ffc2-r1 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-1899ffc2-r2 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-1899ffc2-r3 | ludwig-ai-ludwig-6a122a8e | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-eb82db29-r1 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-eb82db29-r2 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-eb82db29-r3 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-eb82db29-r1 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-eb82db29-r2 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v2-eb82db29-r3 | pyinfra-dev-pyinfra-e7e42b68 | green_no_hidden_tests | green_no_hidden_tests | green_no_hidden_tests | 3/3 | - | same | same |
| v1-1206f641-r3 | rmax-scrapy-redis-8d8672f2 | ci_still_red | ci_still_red | ci_still_red | 0/3 | - | same | same |
| v1-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v1-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v1-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v2-909ef1ea-r1 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v2-909ef1ea-r2 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v2-909ef1ea-r3 | nkanaev-yarr-957e81dd | green_no_hidden_tests | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | DIFFERENT | same |
| v2-d735ebc1-r3 | boyter-scc-4288f7c8 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v1-a352a7c0-r1 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v1-a352a7c0-r2 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v1-a352a7c0-r3 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v2-a352a7c0-r1 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v2-a352a7c0-r2 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |
| v2-a352a7c0-r3 | openbyteinc-quantdinger-733f7bc7 | green_fails_hidden | green_fails_hidden | green_fails_hidden | 3/3 | 0/3 | same | same |

Attempts with an empty patch (not validated): v1-d735ebc1-r1, v1-1206f641-r1, v1-d735ebc1-r2, v1-1206f641-r2, v1-d735ebc1-r3, v2-d735ebc1-r1, v2-1206f641-r1, v2-d735ebc1-r2, v2-1206f641-r2, v2-1206f641-r3.
