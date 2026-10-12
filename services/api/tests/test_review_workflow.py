import hashlib
import unittest

from app.review_workflow import apply_review_decision
from app.schemas import SupportReviewRequest


class SupportReviewWorkflowTests(unittest.TestCase):
    def test_approval_uses_persisted_draft_and_sets_terminal_status(self):
        persisted_draft = "The stored candidate draft."
        request = SupportReviewRequest(
            trace_id="trace-approve",
            reviewer_id="agent-1",
            status="approve",
        )

        response = apply_review_decision(request, ai_draft=persisted_draft)

        self.assertEqual(response.final_draft, persisted_draft)
        self.assertEqual(response.review_status, "approved")
        self.assertEqual(
            response.audit_event_payload.ai_draft_sha256,
            hashlib.sha256(persisted_draft.encode("utf-8")).hexdigest(),
        )

    def test_edit_returns_edited_draft_and_sets_terminal_status(self):
        request = SupportReviewRequest(
            trace_id="trace-edit",
            reviewer_id="agent-1",
            status="edit",
            edited_draft="Corrected response.",
        )

        response = apply_review_decision(request, ai_draft="Original response.")

        self.assertEqual(response.final_draft, "Corrected response.")
        self.assertEqual(response.review_status, "edited")
        self.assertEqual(
            response.audit_event_payload.final_draft_sha256,
            hashlib.sha256(b"Corrected response.").hexdigest(),
        )

    def test_rejection_sets_terminal_status_and_requires_follow_up(self):
        request = SupportReviewRequest(
            trace_id="trace-reject",
            reviewer_id="agent-1",
            status="reject",
            rejection_reason_code="incorrect-facts",
        )

        response = apply_review_decision(request, ai_draft="Unsupported response.")

        self.assertEqual(response.final_draft, "")
        self.assertEqual(response.review_status, "rejected")
        self.assertTrue(response.requires_follow_up)
        self.assertIsNone(response.audit_event_payload.final_draft_sha256)

    def test_edit_requires_non_empty_edited_draft(self):
        request = SupportReviewRequest(
            trace_id="trace-edit",
            reviewer_id="agent-1",
            status="edit",
            edited_draft=" ",
        )

        with self.assertRaisesRegex(ValueError, "edited_draft is required"):
            apply_review_decision(request, ai_draft="Original response.")

    def test_rejection_requires_known_reason_code(self):
        request = SupportReviewRequest(
            trace_id="trace-reject",
            reviewer_id="agent-1",
            status="reject",
        )

        with self.assertRaisesRegex(ValueError, "rejection_reason_code is invalid"):
            apply_review_decision(request, ai_draft="Unsupported response.")


if __name__ == "__main__":
    unittest.main()
