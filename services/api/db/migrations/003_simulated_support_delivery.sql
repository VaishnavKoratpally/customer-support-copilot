BEGIN;

CREATE TABLE IF NOT EXISTS support_delivery_events (
    id UUID PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES support_draft_events(trace_id) ON DELETE CASCADE,
    review_status TEXT NOT NULL CHECK (review_status IN ('not_required', 'approved', 'edited')),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    simulated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT support_delivery_events_trace_unique UNIQUE (trace_id)
);

COMMIT;
