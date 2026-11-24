# Experiment 06 · cache-break reproductions, round c1 (23/11/2026)

Trajectory: the smoke attempt quote-1-t8-l0-r1 (L0), first K = 20 requests (prompts of 5,866 to 46,169 tokens). One reproduction per
condition, max_tokens 0 (no output billed), each with its own attempt id. Sonnet 5.5 prices: input US$ 2, cache write 2.50 (5 min) /
4.00 (1 h), cache read 0.10 per million tokens. Every request answered 200; no input_transformations (no binding header sent).

| condition | what changes | US$ | × R0 | written | of which 1 h | read | read share |
|---|---|---:|---:|---:|---:|---:|---:|
| R0 | control: nothing changed | 0.1602 | 1.0 | 46,166 | 0 | 447,300 | 90.6% |
| R1 | a 'Current time: hh:mm:ss' line at the end of the system prompt, new at every request | 0.9753 | 6.1 | 385,752 | 0 | 107,934 | 21.9% |
| R2 | the two tools in reversed order on every even request | 0.2601 | 1.6 | 87,782 | 0 | 405,684 | 82.2% |
| R3 | effort set to medium from request 11 on (default high) | 0.2226 | 1.4 | 72,158 | 0 | 421,308 | 85.4% |
| R4 | 6-minute pauses before requests 6, 11 and 16 (simulated) | 0.3296 | 2.1 | 116,728 | 0 | 376,738 | 76.3% |
| R4-1h | R4 with every cache marker at ttl 1h | 0.2295 | 1.4 | 46,169 | 46,169 | 447,357 | 90.6% |
| R5 | the request-5 reminder deleted from the history from request 11 on | 0.2002 | 1.2 | 62,838 | 0 | 430,388 | 87.3% |
| R5-sys | the reminder kept; a role:system message with the instruction after request 11's user turn | 0.1603 | 1.0 | 46,187 | 0 | 447,501 | 90.6% |

Total of the 8 reproductions: US$ 2.5379.

Notes (written with the numbers, 23/11):
- R1: the replay sends a request about every second; when two consecutive requests fell in the same second the time line did not
  change and the cache was read (e.g. requests 2 and 3). In a live session, with seconds between requests, the line changes every time,
  so the measured 6.1x is a floor, not a ceiling.
- R2: each tool order keeps its own cache entry, so alternating orders read the entry of two requests back: 1.6x, not a full rewrite.
- R5: the edited history was accepted (no 400): this account is not enforced by the history-editing check, so the break is silent.
  From request 11 the read stops at the prefix before the reminder (9,296 tokens) and the rest is written again once.
- R4-1h: no rewrite after the pauses; the price is every write at 2x. Here 1.4x against R4's 2.1x.
