ALTER TABLE support_draft_events
    ADD COLUMN IF NOT EXISTS evidence_assessment JSONB,
    ADD COLUMN IF NOT EXISTS generation_metadata JSONB;
