from datetime import datetime, timezone
from app.review_taxonomy import VALID_REJECTION_REASONS
from hashlib import sha256
from app.schemas import (
    FinalReviewStatus,
    ReviewAuditEventPayload,
    SupportReviewRequest,
    SupportReviewResponse,
)

def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
def apply_review_decision(
    payload: SupportReviewRequest,
    *,
    ai_draft: str,
) -> SupportReviewResponse:
    if payload.status == "approve":
        final_draft = ai_draft
        requires_follow_up = False
        review_status: FinalReviewStatus = "approved"

    elif payload.status == "edit":
        if payload.edited_draft is None or payload.edited_draft.strip() == "":
            raise ValueError("edited_draft is required when status is 'edit'.")
        final_draft = payload.edited_draft
        requires_follow_up = False
        review_status = "edited"

    else:  # reject
        if payload.rejection_reason_code not in VALID_REJECTION_REASONS:
            raise ValueError("rejection_reason_code is invalid.")
        final_draft = ""
        requires_follow_up = True
        review_status = "rejected"
    
    reviewed_at = datetime.now(timezone.utc)

    audit_event_payload = ReviewAuditEventPayload(
        event_type="support_review_decision_recorded",
        actor_type="agent",
        actor_id=payload.reviewer_id,
        trace_id=payload.trace_id,
        status=payload.status,
        rejection_reason_code=payload.rejection_reason_code,
        requires_follow_up=requires_follow_up,
        reviewed_at=reviewed_at,
        ai_draft_sha256=_sha256_text(ai_draft),
        final_draft_sha256=_sha256_text(final_draft) if final_draft else None,
    )

    return SupportReviewResponse(
        trace_id=payload.trace_id,
        reviewer_id=payload.reviewer_id,
        status=payload.status,
        review_status=review_status,
        final_draft=final_draft,
        requires_follow_up=requires_follow_up,
        reviewed_at=reviewed_at,
        audit_event_payload=audit_event_payload,
    )