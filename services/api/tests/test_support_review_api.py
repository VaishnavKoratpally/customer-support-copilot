import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app import main
from app.persistence import SupportDraftNotFoundError, SupportReviewConflictError
from app.schemas import SupportReviewRequest


class SupportReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.repository.get_pending_review_draft.return_value = "Persisted draft."
        self.idempotency_store = Mock()
        self.idempotency_store.claim.return_value = True
        self.payload = SupportReviewRequest(
            trace_id="trace-1",
            reviewer_id="agent-1",
            status="approve",
        )

    def call_review(self):
        with (
            patch.object(main, "support_repository", self.repository),
            patch.object(main, "review_idempotency_store", self.idempotency_store),
        ):
            return main.review_support_draft(self.payload)

    def test_approval_uses_draft_loaded_by_trace_and_persists_terminal_decision(self):
        response = self.call_review()

        self.assertEqual(response.final_draft, "Persisted draft.")
        self.assertEqual(response.review_status, "approved")
        self.repository.get_pending_review_draft.assert_called_once_with(
            trace_id="trace-1"
        )
        self.repository.save_support_review.assert_called_once()
        self.assertEqual(
            self.repository.save_support_review.call_args.kwargs["ai_draft"],
            "Persisted draft.",
        )

    def test_unknown_trace_returns_not_found_without_claiming_idempotency(self):
        self.repository.get_pending_review_draft.side_effect = (
            SupportDraftNotFoundError("Support draft was not found.")
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_review()

        self.assertEqual(raised.exception.status_code, 404)
        self.idempotency_store.claim.assert_not_called()

    def test_non_pending_trace_returns_conflict_without_claiming_idempotency(self):
        self.repository.get_pending_review_draft.side_effect = (
            SupportReviewConflictError("Support draft is not awaiting human review.")
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_review()

        self.assertEqual(raised.exception.status_code, 409)
        self.idempotency_store.claim.assert_not_called()

    def test_duplicate_review_request_is_not_persisted(self):
        self.idempotency_store.claim.return_value = False

        with self.assertRaises(HTTPException) as raised:
            self.call_review()

        self.assertEqual(raised.exception.status_code, 409)
        self.repository.save_support_review.assert_not_called()

    def test_concurrent_review_conflict_is_returned_as_conflict(self):
        self.repository.save_support_review.side_effect = SupportReviewConflictError(
            "Support draft is no longer awaiting human review."
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_review()

        self.assertEqual(raised.exception.status_code, 409)

    def test_edit_without_edited_text_is_rejected_before_idempotency_claim(self):
        self.payload = SupportReviewRequest(
            trace_id="trace-1",
            reviewer_id="agent-1",
            status="edit",
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_review()

        self.assertEqual(raised.exception.status_code, 400)
        self.idempotency_store.claim.assert_not_called()


if __name__ == "__main__":
    unittest.main()
