from app.schemas import (
    DeliverableReviewStatus,
    DraftMode,
    ReviewLifecycleStatus,
    ReviewStatus,
)


class DeliveryNotAllowedError(RuntimeError):
    pass


def resolve_delivery_content(
    *,
    draft_mode: DraftMode,
    review_status: ReviewLifecycleStatus,
    requires_human_review: bool,
    automation_enabled: bool = False,
    automation_eligible: bool = False,
    draft: str,
    review_action: ReviewStatus | None,
    final_draft: str | None,
) -> tuple[DeliverableReviewStatus, str]:
    if review_status in ("pending_review", "rejected"):
        raise DeliveryNotAllowedError(
            "Human review is pending or the draft was rejected."
        )
    if draft_mode == "preview_only" and review_status != "edited":
        raise DeliveryNotAllowedError(
            "Preview-only drafts must be edited by a human before simulated delivery."
        )

    if review_status == "not_required":
        if draft_mode != "generated":
            raise DeliveryNotAllowedError(
                "Only generated drafts can use the not-required delivery path."
            )
        if requires_human_review:
            raise DeliveryNotAllowedError(
                "The draft requires review but is marked as not requiring review."
            )
        if not automation_enabled:
            raise DeliveryNotAllowedError(
                "A not-required draft cannot be delivered while automation is disabled."
            )
        if not automation_eligible:
            raise DeliveryNotAllowedError(
                "A not-required draft needs a persisted eligible automation decision."
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
