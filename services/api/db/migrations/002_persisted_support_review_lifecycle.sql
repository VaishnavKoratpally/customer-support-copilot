BEGIN;

ALTER TABLE support_draft_events
    ADD COLUMN IF NOT EXISTS review_status TEXT;

UPDATE support_draft_events draft
SET review_status = COALESCE(
    (
        SELECT CASE review.status
            WHEN 'approve' THEN 'approved'
            WHEN 'edit' THEN 'edited'
            WHEN 'reject' THEN 'rejected'
        END
        FROM support_review_events review
        WHERE review.trace_id = draft.trace_id
        ORDER BY review.reviewed_at DESC, review.created_at DESC
        LIMIT 1
    ),
    CASE
        WHEN draft.requires_human_review THEN 'pending_review'
        ELSE 'not_required'
    END
)
WHERE draft.review_status IS NULL;

ALTER TABLE support_draft_events
    ALTER COLUMN review_status SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'support_draft_events_review_status_check'
          AND conrelid = 'support_draft_events'::regclass
    ) THEN
        ALTER TABLE support_draft_events
            ADD CONSTRAINT support_draft_events_review_status_check
            CHECK (
                review_status IN (
                    'not_required',
                    'pending_review',
                    'approved',
                    'edited',
                    'rejected'
                )
            );
    END IF;
END;
$$;

COMMIT;
