# Data Model v0 (Week 1 - Day 2)

This schema supports deterministic support operations plus RAG traceability.

## Operational entities

- `tickets`: lifecycle state for support requests.
- `conversation_messages`: timeline of customer/agent/copilot messages.
- `audit_events`: immutable event log for policy, review, and override actions.
- `support_draft_events`: trace-linked persisted outputs from `/v1/support/draft`.
- `draft_mode`: distinguishes a generated candidate from the current preview-only abstention.
- `support_review_events`: append-only reviewer decisions linked to draft trace, including serialized audit payload.
- `support_delivery_events`: one hash-only receipt for a locally simulated delivery per draft trace.

## Human-review lifecycle

Each `support_draft_events` row stores a `review_status`:

- `pending_review` when `requires_human_review` is true.
- `not_required` when no human review is required.
- A pending draft can transition once to `approved`, `edited`, or `rejected`.

`POST /v1/support/review` accepts a trace ID and a decision, then loads the
canonical draft from `support_draft_events`; it does not trust draft text from
the caller. In one PostgreSQL transaction, it locks the draft row, verifies it
is still pending, changes its status, and appends the review event. Unknown
traces return 404; drafts that are not pending return 409. Redis idempotency
still rejects duplicate requests, while the database transition is the source
of truth for whether a draft can be reviewed.

`POST /v1/support/simulated-deliveries` accepts only a trace ID. It locks the
draft row and selects the canonical text: the saved candidate for
`not_required`, or the persisted final review text for `approved`/`edited`.
Pending and rejected drafts return 409. The endpoint records the eligible
review state, a SHA-256 content hash, and a timestamp; a unique trace constraint
allows at most one simulated delivery per draft. It stores no duplicate message
body and makes no network call.

This is a local server-side gate, not actual customer delivery. `/v1/support/draft`
still returns its candidate, so clients can bypass the simulation by copying
that text elsewhere. A future real sender must use only `not_required`,
`approved`, or `edited` state and should use a transactional outbox rather than
holding a database transaction open across an external network call. Reviewer
identity is also caller-supplied until authentication is implemented.

The current `/v1/support/draft` runtime is `preview_only`: it returns real
retrieved chunks and a deterministic abstention notice, not a generated
customer response. Its retrieval and answer confidence fields are `NULL`
because neither score is calibrated or computed. Preview-only drafts require
review, cannot be approved as customer responses, and can enter simulated
delivery only after a human edit. A generated-mode draft retains the existing
review and delivery rules.

## Knowledge entities

- `source_documents`: canonical support knowledge assets with metadata and versioning.
- `document_chunks`: chunked content with vector embeddings for retrieval.

## Why this shape

1. `source_documents` and `document_chunks` are split to preserve both original content and retrieval units.
2. `audit_events` is append-only to support post-incident and compliance analysis.
3. `ticket_id` foreign keys keep all actions traceable at the ticket level.
4. `support_draft_events` and `support_review_events` preserve Week 2 runtime behavior even when ticket orchestration is not yet wired into request flows.

## Notes

- Embedding dimension is set to 1024 for the initial local embedding baseline.
- If you switch embedding model dimensions later, create a dedicated migration and re-embed chunks.
- updated_at is maintained by DB triggers for tickets and source_documents to avoid missed timestamp updates across write paths.
