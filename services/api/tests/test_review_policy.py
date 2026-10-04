import unittest

from app.review_policy import evaluate_review_policy


class ReviewPolicyComplianceTests(unittest.TestCase):
    def decide(self, **overrides):
        inputs = {
            "intent": "general_support",
            "answer_confidence": 0.9,
            "answer_confidence_threshold": 0.65,
            "citation_contract_passed": True,
        }
        inputs.update(overrides)
        return evaluate_review_policy(**inputs)

    def test_each_high_risk_intent_requires_review(self):
        for intent in ("billing_dispute", "account_security", "legal"):
            with self.subTest(intent=intent):
                decision = self.decide(intent=intent)
                self.assertTrue(decision.requires_human_review)
                self.assertEqual(decision.triggers, ["high_risk_intent"])

    def test_below_threshold_requires_review(self):
        decision = self.decide(answer_confidence=0.64)
        self.assertTrue(decision.requires_human_review)
        self.assertEqual(decision.triggers, ["low_answer_confidence"])

    def test_missing_citations_requires_review(self):
        decision = self.decide(citation_contract_passed=False)
        self.assertTrue(decision.requires_human_review)
        self.assertEqual(decision.triggers, ["missing_citations"])

    def test_confident_cited_low_risk_draft_does_not_require_review(self):
        decision = self.decide()
        self.assertFalse(decision.requires_human_review)
        self.assertEqual(decision.triggers, [])

    def test_confidence_equal_to_threshold_is_not_below_threshold(self):
        decision = self.decide(answer_confidence=0.65)
        self.assertFalse(decision.requires_human_review)
        self.assertEqual(decision.triggers, [])

    def test_all_applicable_triggers_are_reported(self):
        decision = self.decide(
            intent="legal",
            answer_confidence=0.4,
            citation_contract_passed=False,
        )
        self.assertTrue(decision.requires_human_review)
        self.assertCountEqual(
            decision.triggers,
            ["high_risk_intent", "low_answer_confidence", "missing_citations"],
        )


if __name__ == "__main__":
    unittest.main()