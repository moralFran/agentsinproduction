# v1: summary of the collection (12/11/2026, 09:11–10:21 UTC; 11 cases × 3 repetitions, protocol order)

> Translated from the Portuguese original, written right after the v1 collection (before v2 and before any judging).

No judgement of merit: the 21 green patches are in `results/blind/packets/` (random ids, no version or round; the key
is in `results/blind/key.jsonl` and must not be opened before the blind judging, which must wait for v2).

| Outcome | Attempts |
|---|---|
| green, case has no hidden tests | 9 |
| green and passed the maintainer's hidden tests | 6 |
| green and FAILED the hidden tests (by the protocol's rule: "worse") | 6 |
| CI still red | 7 |
| gave up (ended without a patch) | 2 |
| stopped by the per-attempt limit (budget), no patch | 3 |
| did not apply / rejected by the validator / infrastructure error | 0 / 0 / 0 |

Real cost (gateway): US$ 2.435 over the 33 attempts (mean US$ 0.074, max US$ 0.180). None reached US$ 0.33.

The 3 budget stops are the 3 repetitions of `boyter/scc` (`d735ebc1`): real spend US$ 0.173 / 0.180 / 0.176, with 25 / 24
/ 24 calls. The refused call reserved US$ 0.162 / 0.165 / 0.158 with US$ 0.157 / 0.150 / 0.154 left: an input estimate of
~47–50 thousand tokens (a request of ~87–93 KB ÷ 2 + 2,000) and 4,096 output, while the real input of the last calls was
~27–29 thousand tokens (the estimate is ~1.7× higher) and the real cost per call ~US$ 0.01. In all three the agent was
still investigating (looking for `languages.json` and comparing lists of languages; in the third it was writing a
temporary comparison test) and had no patch. Estimate: 3 of the 33 attempts were ended by the reservation with real
spend below US$ 0.33; no other came close (the next most expensive spent US$ 0.138).
