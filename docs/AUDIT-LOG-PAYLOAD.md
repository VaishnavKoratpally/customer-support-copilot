# Audit Log Payload for Review Actions (Day 5)

## Purpose

Define a structured audit payload for support review decisions (`approve`, `edit`, `reject`) so every human intervention is:

- traceable,
- consistent,
- analyzable,
- integrity-verifiable.

## Scope

This payload is produced by the review workflow (`POST /v1/support/review`) and is designed to be stored in `audit_events.payload` (JSONB) in Postgres.

## Event contract

### event_type
- Fixed value: `support_review_decision_recorded`
- Why: makes event filtering and reporting deterministic.

### actor
- `actor_type`: `agent`
- `actor_id`: reviewer identity (e.g., `agent-01`)
- Why: captures who made the decision.

### trace and decision
- `trace_id`: links review event back to the original AI draft request
- `status`: one of `approve`, `edit`, `reject`
- `requires_follow_up`: whether additional action is required

### rejection context
- `rejection_reason_code`: required when `status=reject`, otherwise null
- Values constrained by taxonomy in `REJECTION-REASON-TAXONOMY.md`

### timing
- `reviewed_at`: UTC timestamp at decision time

### integrity fields
- `ai_draft_sha256`: SHA-256 hash of original AI draft text
- `final_draft_sha256`: SHA-256 hash of final draft text when present, else null

Why hashes:
1. verify text integrity without storing full text in broad audit records
2. reduce sensitive content exposure in event logs
3. support tamper-evidence checks during investigations

## Example payload

```json
{
  "event_type": "support_review_decision_recorded",
  "actor_type": "agent",
  "actor_id": "agent-01",
  "trace_id": "t-10",
  "status": "edit",
  "rejection_reason_code": null,
  "requires_follow_up": false,
  "reviewed_at": "2026-09-18T17:50:10.123456+00:00",
  "ai_draft_sha256": "6d3f3f12d4d0bc42b7f3f8d56bf4b91e2ec3c24e16b8d48a35b4dbf33ec0c3dd",
  "final_draft_sha256": "a2bb96544f737a1f8f13f0de16f6865f8aa2d0a7c4d6a4519d90b9f38138a1f4"
}