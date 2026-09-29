# Data Model v0 (Week 1 - Day 2)

This schema supports deterministic support operations plus RAG traceability.

## Operational entities

- `tickets`: lifecycle state for support requests.
- `conversation_messages`: timeline of customer/agent/copilot messages.
- `audit_events`: immutable event log for policy, review, and override actions.
- `support_draft_events`: trace-linked persisted outputs from `/v1/support/draft`.
- `support_review_events`: reviewer decisions linked to draft trace, including serialized audit payload.

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
