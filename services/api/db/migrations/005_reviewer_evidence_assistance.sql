BEGIN;

CREATE TABLE IF NOT EXISTS reviewer_assessment_events (
    assessment_id UUID PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES support_draft_events(trace_id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('running', 'completed', 'failed')),
    assessor_model TEXT NOT NULL,
    system_prompt_sha256 TEXT NOT NULL CHECK (system_prompt_sha256 ~ '^[0-9a-f]{64}$'),
    schema_sha256 TEXT NOT NULL CHECK (schema_sha256 ~ '^[0-9a-f]{64}$'),
    proposed_assessment JSONB,
    error JSONB,
    generation_metrics JSONB,
    elapsed_seconds DOUBLE PRECISION CHECK (elapsed_seconds >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CHECK (
        (state = 'running' AND proposed_assessment IS NULL AND error IS NULL
            AND generation_metrics IS NULL AND elapsed_seconds IS NULL AND completed_at IS NULL)
        OR (state = 'completed' AND proposed_assessment IS NOT NULL AND error IS NULL
            AND elapsed_seconds IS NOT NULL AND completed_at IS NOT NULL)
        OR (state = 'failed' AND proposed_assessment IS NULL AND error IS NOT NULL
            AND elapsed_seconds IS NOT NULL AND completed_at IS NOT NULL)
    ),
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_reviewer_assessment_events_trace_started
ON reviewer_assessment_events (trace_id, started_at);

CREATE TABLE IF NOT EXISTS reviewer_assessment_feedback (
    feedback_id UUID PRIMARY KEY,
    assessment_id UUID NOT NULL REFERENCES reviewer_assessment_events(assessment_id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('helpful', 'needs_correction', 'unusable')),
    reasons JSONB NOT NULL CHECK (jsonb_typeof(reasons) = 'array'),
    corrected_status TEXT CHECK (
        corrected_status IN ('sufficient', 'partial', 'insufficient', 'none', 'clarification_needed', 'conflicting')
    ),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assessment_id, reviewer_id)
);

COMMIT;
