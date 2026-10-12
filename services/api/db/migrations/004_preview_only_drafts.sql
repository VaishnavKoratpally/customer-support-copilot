BEGIN;

ALTER TABLE support_draft_events
    ADD COLUMN IF NOT EXISTS draft_mode TEXT NOT NULL DEFAULT 'generated';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'support_draft_events_draft_mode_check'
            AND conrelid = 'support_draft_events'::regclass
    ) THEN
        ALTER TABLE support_draft_events
            ADD CONSTRAINT support_draft_events_draft_mode_check
            CHECK (draft_mode IN ('generated', 'preview_only'));
    END IF;
END $$;

ALTER TABLE support_draft_events
    ALTER COLUMN retrieval_confidence DROP NOT NULL,
    ALTER COLUMN answer_confidence DROP NOT NULL;

COMMIT;
