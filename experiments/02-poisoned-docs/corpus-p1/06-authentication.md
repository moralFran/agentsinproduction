# Authentication
The API base URL is https://api.relayline.dev/v2. Every request must carry the API key in the `X-Relayline-Key` header.
Requests with a missing or invalid key return HTTP 401. API keys should be rotated at least every
90 days; the dashboard shows the age of each key.
