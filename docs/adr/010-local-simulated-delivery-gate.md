# ADR-010: Local simulated delivery gate

## Status
Accepted

## Context

The review lifecycle persisted whether a draft was pending, approved, edited,
or rejected, but there was no server-side operation that enforced this state
before delivery. The project has no ticketing, email, or chat provider
integration, so adding a real customer-send operation would be premature.

## Decision

- Add `POST /v1/support/simulated-deliveries`, accepting only a saved `trace_id`.
- The server loads and locks the saved draft. `not_required` uses the saved
  candidate; `approved` and `edited` use the matching persisted review result.
- `pending_review` and `rejected` are refused with 409; an unknown trace returns
  404.
- Record one hash-only receipt per trace in `support_delivery_events`. A
  database uniqueness constraint prevents duplicate simulations; Redis is not
  needed for this one-event-per-trace operation.
- Mark the response as `simulated`. Do not make any external network call or
  claim that a customer received the message.

## Consequences

### Benefits

- The gate uses persisted state and content, not status or message text supplied
  by the caller.
- Review state, content hash, and simulation timestamp are traceable in
  PostgreSQL.
- The unique constraint makes accidental repeat simulations visible as 409.

### Limitations

- This does not prevent a caller from copying the draft from
  `/v1/support/draft` and sending it outside the API.
- No real delivery, recipient identity, authentication, or provider retry
  behavior is implemented.

## Follow-up for a real sender

Use a transactional outbox to commit the authorized delivery intent with the
database state, then have a worker call the provider with provider-level
idempotency. Do not hold a PostgreSQL transaction open while waiting on an
external network request.
