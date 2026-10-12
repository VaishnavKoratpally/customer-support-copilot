import unittest

from app.delivery_workflow import DeliveryNotAllowedError, resolve_delivery_content


class DeliveryWorkflowTests(unittest.TestCase):
    def test_not_required_draft_uses_persisted_candidate(self):
        status, content = resolve_delivery_content(
            draft_mode="generated",
            review_status="not_required",
            requires_human_review=False,
            draft="Persisted candidate.",
            review_action=None,
            final_draft=None,
        )

        self.assertEqual(status, "not_required")
        self.assertEqual(content, "Persisted candidate.")

    def test_approved_draft_uses_persisted_review_final(self):
        status, content = resolve_delivery_content(
            draft_mode="generated",
            review_status="approved",
            requires_human_review=True,
            draft="Original candidate.",
            review_action="approve",
            final_draft="Approved final.",
        )

        self.assertEqual(status, "approved")
        self.assertEqual(content, "Approved final.")

    def test_edited_draft_uses_persisted_review_final(self):
        status, content = resolve_delivery_content(
            draft_mode="generated",
            review_status="edited",
            requires_human_review=True,
            draft="Original candidate.",
            review_action="edit",
            final_draft="Human-edited final.",
        )

        self.assertEqual(status, "edited")
        self.assertEqual(content, "Human-edited final.")

    def test_pending_and_rejected_drafts_are_not_deliverable(self):
        for status in ("pending_review", "rejected"):
            with self.subTest(review_status=status):
                with self.assertRaises(DeliveryNotAllowedError):
                    resolve_delivery_content(
                        draft_mode="generated",
                        review_status=status,
                        requires_human_review=True,
                        draft="Persisted candidate.",
                        review_action=None,
                        final_draft=None,
                    )

    def test_review_state_requires_matching_decision_and_non_empty_final(self):
        with self.assertRaises(DeliveryNotAllowedError):
            resolve_delivery_content(
                draft_mode="generated",
                review_status="approved",
                requires_human_review=True,
                draft="Original candidate.",
                review_action="edit",
                final_draft="Approved final.",
            )
        with self.assertRaises(DeliveryNotAllowedError):
            resolve_delivery_content(
                draft_mode="generated",
                review_status="edited",
                requires_human_review=True,
                draft="Original candidate.",
                review_action="edit",
                final_draft=" ",
            )

    def test_not_required_state_cannot_bypass_required_review_flag(self):
        with self.assertRaises(DeliveryNotAllowedError):
            resolve_delivery_content(
                draft_mode="generated",
                review_status="not_required",
                requires_human_review=True,
                draft="Persisted candidate.",
                review_action=None,
                final_draft=None,
            )

    def test_preview_only_draft_cannot_be_approved_or_delivered_unedited(self):
        for status, action in (
            ("not_required", None),
            ("approved", "approve"),
        ):
            with self.subTest(review_status=status):
                with self.assertRaises(DeliveryNotAllowedError):
                    resolve_delivery_content(
                        draft_mode="preview_only",
                        review_status=status,
                        requires_human_review=True,
                        draft="Preview notice.",
                        review_action=action,
                        final_draft="Preview notice.",
                    )

    def test_preview_only_draft_can_be_delivered_after_human_edit(self):
        status, content = resolve_delivery_content(
            draft_mode="preview_only",
            review_status="edited",
            requires_human_review=True,
            draft="Preview notice.",
            review_action="edit",
            final_draft="Human-authored customer response.",
        )

        self.assertEqual(status, "edited")
        self.assertEqual(content, "Human-authored customer response.")


if __name__ == "__main__":
    unittest.main()
