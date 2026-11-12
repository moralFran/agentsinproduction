# v1 × v2: outcomes per case and per attempt (no judgement of merit)

> Header translated from the Portuguese original; the block below is the script output, unchanged.

v2 = v1 + one instruction in the prompt (amendment 23). v2 collection: 2026-11-12 10:26–11:37 UTC. Blind packets: 43 (v1 21,
v2 22) in a single pool, ids and order re-randomised (`cases/blind-shuffle.py`); judge before opening `results/blind/key.jsonl`.

```
case                   v1 r1 / r2 / r3                                      | v2 r1 / r2 / r3
OpenByteInc/QuantDinge green, hidden FAIL / green, hidden FAIL / green, hidden FAIL | green, hidden FAIL / green, hidden FAIL / green, hidden FAIL
ludwig-ai/ludwig       green (no hidden) / green (no hidden) / green (no hidden) | green (no hidden) / green (no hidden) / green (no hidden)
mark3labs/mcp-go       still red         / still red         / still red         | still red / still red / still red
boyter/scc             budget stop       / budget stop       / budget stop       | budget stop / budget stop / green, hidden FAIL
gobwas/ws              green, hidden FAIL / green, hidden FAIL / green, hidden FAIL | green, hidden FAIL / green+hidden ok / green+hidden ok
sigstore/cosign        green+hidden ok   / green+hidden ok   / green+hidden ok   | green+hidden ok / green+hidden ok / green+hidden ok
pyinfra-dev/pyinfra    green (no hidden) / green (no hidden) / green (no hidden) | green (no hidden) / green (no hidden) / green (no hidden)
rmax/scrapy-redis      gave up           / gave up           / still red         | gave up / gave up / gave up
tdewolff/minify        green+hidden ok   / green+hidden ok   / green+hidden ok   | green+hidden ok / green+hidden ok / green+hidden ok
nkanaev/yarr           green (no hidden) / green (no hidden) / green (no hidden) | green (no hidden) / green (no hidden) / green (no hidden)
alicebob/miniredis     still red         / still red         / still red         | still red / still red / still red
v1: green (no hidden) 9, still red 7, green, hidden FAIL 6, green+hidden ok 6, budget stop 3, gave up 2 | US$ 2.435 (mean 0.0738, max 0.180) | calls 317
v2: green (no hidden) 9, green+hidden ok 8, still red 6, green, hidden FAIL 5, gave up 3, budget stop 2 | US$ 2.559 (mean 0.0776, max 0.178) | calls 314
v2 per attempt (run, USD, calls, tools, agent s):
  v2-a352a7c0-r1   OpenByteInc/QuantDin 0.087 10 10 50
  v2-1899ffc2-r1   ludwig-ai/ludwig     0.064 9 9 309
  v2-bbbe6833-r1   mark3labs/mcp-go     0.104 12 12 175
  v2-d735ebc1-r1   boyter/scc           0.174 20 22 286
  v2-e88f0806-r1   gobwas/ws            0.142 13 13 668
  v2-c2452a82-r1   sigstore/cosign      0.026 5 5 274
  v2-eb82db29-r1   pyinfra-dev/pyinfra  0.053 10 10 38
  v2-1206f641-r1   rmax/scrapy-redis    0.044 4 4 23
  v2-69bc3125-r1   tdewolff/minify      0.117 12 12 112
  v2-909ef1ea-r1   nkanaev/yarr         0.041 6 6 70
  v2-56d24d7d-r1   alicebob/miniredis   0.028 4 4 67
  v2-a352a7c0-r2   OpenByteInc/QuantDin 0.073 8 7 51
  v2-1899ffc2-r2   ludwig-ai/ludwig     0.079 13 13 425
  v2-bbbe6833-r2   mark3labs/mcp-go     0.079 9 9 183
  v2-d735ebc1-r2   boyter/scc           0.178 23 24 275
  v2-e88f0806-r2   gobwas/ws            0.135 12 12 665
  v2-c2452a82-r2   sigstore/cosign      0.027 5 5 262
  v2-eb82db29-r2   pyinfra-dev/pyinfra  0.065 12 12 60
  v2-1206f641-r2   rmax/scrapy-redis    0.067 7 7 42
  v2-69bc3125-r2   tdewolff/minify      0.083 8 8 90
  v2-909ef1ea-r2   nkanaev/yarr         0.042 6 6 54
  v2-56d24d7d-r2   alicebob/miniredis   0.041 5 5 55
  v2-a352a7c0-r3   OpenByteInc/QuantDin 0.064 8 8 44
  v2-1899ffc2-r3   ludwig-ai/ludwig     0.055 8 8 208
  v2-bbbe6833-r3   mark3labs/mcp-go     0.073 8 8 175
  v2-d735ebc1-r3   boyter/scc           0.168 24 24 293
  v2-e88f0806-r3   gobwas/ws            0.144 14 14 681
  v2-c2452a82-r3   sigstore/cosign      0.029 5 5 268
  v2-eb82db29-r3   pyinfra-dev/pyinfra  0.045 8 8 42
  v2-1206f641-r3   rmax/scrapy-redis    0.050 6 5 28
  v2-69bc3125-r3   tdewolff/minify      0.105 9 9 99
  v2-909ef1ea-r3   nkanaev/yarr         0.040 6 6 62
  v2-56d24d7d-r3   alicebob/miniredis   0.038 5 5 67
refused: v2-d735ebc1-r1 run budget: this call reserves $0.1573, $0.1558 left in run v2-d735ebc1-r1
refused: v2-d735ebc1-r2 run budget: this call reserves $0.1638, $0.1521 left in run v2-d735ebc1-r2
```
