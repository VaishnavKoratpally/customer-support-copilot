# ADR 00X: Redis idempotency guard for support review endpoint

## Status
Accepted

## Context
`/v1/support/review` is a side-effecting endpoint (audit-linked decision write). Retries, double-clicks, or network replay can create duplicate review records.

## Decision
Use Redis as an idempotency guard for `/v1/support/review`:
- Compute deterministic key from review payload fields.
- `SET key value NX EX <ttl>` to claim first writer.
- If key already exists, return 409 duplicate.
- If Redis is unavailable, fail closed with 503.

## Consequences
### Benefits
- Prevents duplicate review side effects.
- Improves audit integrity and operational safety.

### Costs
- Additional Redis dependency on write path.
- Need key design discipline and TTL tuning.

### Risks
- False duplicates if key composition is too coarse.
- Temporary write unavailability when Redis is down.

## Alternatives considered
1. Retrieval cache first (faster reads but does not protect write correctness).
2. DB-only dedupe constraints (less flexible for replay windows and request-shape matching).