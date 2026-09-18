from datetime import datetime, timezone
from app.review_taxonomy import VALID_REJECTION_REASONS

from app.schemas import SupportReviewRequest, SupportReviewResponse


def apply_review_decision(payload: SupportReviewRequest) -> SupportReviewResponse:
    if payload.status == "approve":
        final_draft = payload.ai_draft
        requires_follow_up = False

    elif payload.status == "edit":
        if payload.edited_draft is None or payload.edited_draft.strip() == "":
            raise ValueError("edited_draft is required when status is 'edit'.")
        final_draft = payload.edited_draft
        requires_follow_up = False

    else:  # reject
        if payload.rejection_reason_code not in VALID_REJECTION_REASONS:
            raise ValueError("rejection_reason_code is invalid.")
        final_draft = ""
        requires_follow_up = True

    return SupportReviewResponse(
        trace_id=payload.trace_id,
        reviewer_id=payload.reviewer_id,
        status=payload.status,
        final_draft=final_draft,
        requires_follow_up=requires_follow_up,
        reviewed_at=datetime.now(timezone.utc),
    )