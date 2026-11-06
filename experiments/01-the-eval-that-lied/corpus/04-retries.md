# Retries and dead letters
Failed deliveries are retried up to 8 times with exponential backoff, starting at
5 seconds and capped at 2 hours. After the last retry the event moves to the
dead-letter queue, where it is kept for 7 days and can be replayed from the dashboard or the CLI.
Replaying a dead-lettered event that has already expired returns HTTP 410.
