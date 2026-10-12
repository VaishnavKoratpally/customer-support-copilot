from app.schemas import (
    DeliverableReviewStatus,
    ReviewLifecycleStatus,
    ReviewStatus,
)


class DeliveryNotAllowedError(RuntimeError):
    pass


def resolve_delivery_content(
    *,
    review_status: ReviewLifecycleStatus,
    requires_human_review: bool,
    draft: str,
    review_action: ReviewStatus | None,
    final_draft: str | None,
) -> tuple[DeliverableReviewStatus, str]:
    if review_status == "not_required":
        if requires_human_review:
            raise DeliveryNotAllowedError(
                "The draft requires review but is marked as not requiring review."
            )
        if draft.strip() == "":
            raise DeliveryNotAllowedError("The persisted draft is empty.")
        return review_status, draft

    if review_status == "approved":
        expected_action: ReviewStatus = "approve"
    elif review_status == "edited":
        expected_action = "edit"
    else:
        raise DeliveryNotAllowedError(
            "Human review is pending or the draft was rejected."
        )

    if review_action != expected_action:
        raise DeliveryNotAllowedError(
            "The persisted review decision does not match the draft status."
        )
    if final_draft is None or final_draft.strip() == "":
        raise DeliveryNotAllowedError("The reviewed final draft is empty.")

    return review_status, final_draft
