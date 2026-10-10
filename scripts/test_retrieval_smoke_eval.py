import unittest

from retrieval_smoke_eval import evaluate_case, summarize_results


class RetrievalSmokeEvaluationTests(unittest.TestCase):
    def test_recall_and_precision_are_computed_from_unique_sources(self):
        case = {
            "id": "multi-source-case",
            "expected_retrieval_source_ids": ["billing-policy-01", "support-sla-02"],
        }
        response = {
            "hits": [
                {"source_id": "billing-policy-01", "cosine_distance": 0.1},
                {"source_id": "billing-policy-01", "cosine_distance": 0.2},
                {"source_id": "support-sla-02", "cosine_distance": 0.3},
                {"source_id": "account-recovery-01", "cosine_distance": 0.4},
            ]
        }

        result = evaluate_case(case, response, top_k=4)

        self.assertEqual(result["recall_at_k"], 1.0)
        self.assertAlmostEqual(result["source_precision_at_k"], 0.67)
        self.assertEqual(result["non_expected_source_ids"], ["account-recovery-01"])

    def test_recall_is_fraction_of_expected_sources_found(self):
        case = {
            "id": "multi-source-case",
            "expected_retrieval_source_ids": ["billing-policy-01", "support-sla-02"],
        }
        response = {
            "hits": [
                {"source_id": "billing-policy-01", "cosine_distance": 0.1},
                {"source_id": "account-recovery-01", "cosine_distance": 0.4},
            ]
        }

        result = evaluate_case(case, response, top_k=2)

        self.assertEqual(result["recall_at_k"], 0.5)

    def test_out_of_corpus_case_has_no_recall_or_precision_score(self):
        case = {
            "id": "out-of-corpus-case",
            "expected_retrieval_source_ids": [],
        }
        response = {
            "hits": [
                {"source_id": "billing-policy-01", "cosine_distance": 0.53},
            ]
        }

        result = evaluate_case(case, response, top_k=1)

        self.assertIsNone(result["recall_at_k"])
        self.assertIsNone(result["source_precision_at_k"])
        self.assertEqual(result["nearest_cosine_distance"], 0.53)

    def test_summary_groups_metrics_by_top_k(self):
        results = [
            {
                "top_k": 1,
                "recall_at_k": 0.5,
                "source_precision_at_k": 1.0,
            },
            {
                "top_k": 3,
                "recall_at_k": 1.0,
                "source_precision_at_k": 0.5,
            },
        ]

        summary = summarize_results(results)

        self.assertEqual(summary["1"]["mean_source_recall_at_k"], 0.5)
        self.assertEqual(summary["3"]["mean_source_recall_at_k"], 1.0)
        self.assertFalse(summary["1"]["source_recall_target_met"])
        self.assertTrue(summary["3"]["source_recall_target_met"])


if __name__ == "__main__":
    unittest.main()
