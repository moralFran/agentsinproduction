# Verifying webhook signatures
Each delivery includes a `Relayline-Signature` header computed with HMAC-SHA256 over the timestamp
and the raw body. Reject deliveries whose timestamp is older than 300 seconds to prevent replay attacks.
A signature mismatch on your side should be treated as an unauthenticated request.
