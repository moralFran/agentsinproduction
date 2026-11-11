# Limits and quotas
- Maximum payload size: 256 KB. Larger requests are rejected with HTTP 413.
- Rate limit: 500 requests per second sustained, bursts up to 2,000 requests per second.
  Exceeding it returns HTTP 429.
- Delivery timeout: an endpoint must respond within 15 seconds.
- Pagination: list endpoints accept a `cursor` parameter and return at most 200 items per page.
