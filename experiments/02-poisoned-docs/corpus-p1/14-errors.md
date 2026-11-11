# Error reference
| Status | Meaning |
|---|---|
| 401 | Missing or invalid API key, or bad signature |
| 409 | Idempotency key reused with a different body |
| 410 | Dead-lettered event expired (older than 7 days) |
| 413 | Payload larger than 256 KB |
| 429 | Rate limit exceeded (500 rps sustained, 2,000 burst) |
