# ADR-009: Persisted support draft review lifecycle

## Status
Accepted

## Context

The draft endpoint persisted `requires_human_review` as a boolean, but that
flag did not represent whether a review decision had happened. The review
endpoint also accepted draft text from the caller and could record a decision
without checking the saved draft or preventing a later, conflicting decision
for the same trace.

## Decision

- Persist `review_status` on each support draft:
  - `pending_review` when human review is required.
  - `not_required` otherwise.
  - `approved`, `edited`, or `rejected` after the one permitted decision.
- The review request identifies the saved draft by `trace_id` and does not
  include draft text. The API loads the canonical draft from PostgreSQL.
- The repository locks the draft row, verifies it is pending, updates its
  status, and inserts the review event in a single transaction.
- Return 404 for an unknown trace and 409 when the draft is not awaiting
  review. Redis idempotency remains as an early duplicate-request guard; the
  database state is authoritative.
- Backfill existing drafts from their latest review event when present;
  otherwise derive the initial status from `requires_human_review`.

## Consequences

### Benefits

- Review decisions are bound to the persisted candidate instead of
  caller-supplied text.
- Concurrent or later decisions cannot transition the same draft a second
  time.
- Review status is queryable without inferring it from review-event history.

### Limitations

- `/v1/support/draft` still returns its candidate even when review is pending.
  There is no customer-facing send endpoint, so this lifecycle does not by
  itself prevent an external caller from sending an unapproved draft.
- Reviewer identity is caller-supplied; authentication and authorization are
  not implemented.
- The lifecycle records a decision, but does not establish that the draft's
  claims are factually grounded.

## Alternatives considered

1. Keep `requires_human_review` as a response-only flag. This does not persist
   or enforce a review transition.
2. Continue trusting the draft text in the review request. This permits a
   decision to be recorded against text different from the saved trace.
3. Treat Redis idempotency as the lifecycle store. Redis does not provide the
   durable, trace-linked audit state needed for review history.
