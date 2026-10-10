import unittest

from citation_correctness_eval import evaluate_case as evaluate_citation_case
from groundedness_eval import evaluate_case as evaluate_groundedness_case


class DraftQualityMetricTests(unittest.TestCase):
    def test_correct_citation_ids_do_not_prove_draft_claims_are_supported(self):
        source_ids = ["billing-policy-01", "support-sla-02"]
        response = {
            "draft": "We guarantee an immediate refund. A support agent will manually review your case.",
            "citation_source_ids": source_ids,
            "citation_contract_passed": True,
        }
        citation_case = {
            "id": "same-draft",
            "expected_source_ids": source_ids,
            "allow_extra_citations": False,
        }
        groundedness_case = {
            "id": "same-draft",
            "required_phrases": ["2 business days", "human review"],
            "forbidden_phrases": ["guaranteed refund", "immediate refund"],
            "expected_source_ids": source_ids,
        }

        citation_result = evaluate_citation_case(citation_case, response)
        groundedness_result = evaluate_groundedness_case(
            groundedness_case,
            response,
        )

        self.assertTrue(citation_result["passed"])
        self.assertEqual(citation_result["precision"], 1.0)
        self.assertEqual(citation_result["recall"], 1.0)
        self.assertFalse(groundedness_result["passed"])
        self.assertFalse(
            groundedness_result["forbidden_phrase_checks"]["immediate refund"]
        )

    def test_groundedness_literal_check_can_miss_a_paraphrase(self):
        response = {
            "draft": "Our team will review this manually within 2 business days.",
            "citation_source_ids": ["support-sla-02"],
            "citation_contract_passed": True,
        }
        case = {
            "id": "paraphrased-review",
            "required_phrases": ["human review", "2 business days"],
            "forbidden_phrases": [],
            "expected_source_ids": ["support-sla-02"],
        }

        result = evaluate_groundedness_case(case, response)

        self.assertFalse(result["required_phrase_checks"]["human review"])
        self.assertTrue(result["required_phrase_checks"]["2 business days"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
