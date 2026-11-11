# Idempotency
Send an `Idempotency-Key` header to make event creation safe to retry. Relayline remembers keys for
24 hours; a repeated key with a different body inside that window returns HTTP 409.
