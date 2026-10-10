import math
import unittest

from retrieval_distance_threshold_eval import (
    build_case_rows,
    score_threshold,
    threshold_candidates,
)


class RetrievalDistanceThresholdEvaluationTests(unittest.TestCase):
    def test_threshold_candidates_cover_decision_boundaries(self):
        rows = [
            {"nearest_cosine_distance": 0.2},
            {"nearest_cosine_distance": 0.5},
        ]

        candidates = threshold_candidates(rows)

        self.assertEqual(candidates[0], math.nextafter(0.2, -math.inf))
        self.assertAlmostEqual(candidates[1], 0.35)
        self.assertEqual(candidates[2], math.nextafter(0.5, math.inf))

    def test_threshold_reports_false_accepts_and_false_rejects(self):
        rows = [
            {"expected_source_present": True, "nearest_cosine_distance": 0.2},
            {"expected_source_present": True, "nearest_cosine_distance": 0.6},
            {"expected_source_present": False, "nearest_cosine_distance": 0.3},
            {"expected_source_present": False, "nearest_cosine_distance": 0.7},
        ]

        result = score_threshold(rows, threshold=0.4)

        self.assertEqual(
            result["confusion_matrix"],
            {
                "true_source_present": 1,
                "false_source_present": 1,
                "true_source_absent": 1,
                "false_source_absent": 1,
            },
        )
        self.assertEqual(result["metrics"]["source_presence_recall"], 0.5)
        self.assertEqual(result["metrics"]["no_source_detection_recall"], 0.5)
        self.assertEqual(result["metrics"]["false_accept_rate"], 0.5)
        self.assertEqual(result["metrics"]["false_reject_rate"], 0.5)

    def test_relevant_source_does_not_imply_sufficient_evidence(self):
        dataset_cases = [
            {
                "id": "reset-expiry",
                "expected_retrieval_source_ids": ["account-recovery-01"],
                "evidence_sufficiency": "insufficient",
            }
        ]
        retrieval_artifact = {
            "results": [
                {
                    "id": "reset-expiry",
                    "top_k": 1,
                    "expected_source_ids": ["account-recovery-01"],
                    "nearest_cosine_distance": 0.3,
                }
            ]
        }

        rows = build_case_rows(dataset_cases, retrieval_artifact, top_k=1)

        self.assertTrue(rows[0]["expected_source_present"])
        self.assertEqual(rows[0]["evidence_sufficiency"], "insufficient")

    def test_rejects_artifact_with_mismatched_expected_source_labels(self):
        dataset_cases = [
            {
                "id": "case-1",
                "expected_retrieval_source_ids": ["billing-policy-01"],
                "evidence_sufficiency": "sufficient",
            }
        ]
        retrieval_artifact = {
            "results": [
                {
                    "id": "case-1",
                    "top_k": 1,
                    "expected_source_ids": [],
                    "nearest_cosine_distance": 0.2,
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "expected-source labels differ"):
            build_case_rows(dataset_cases, retrieval_artifact, top_k=1)


if __name__ == "__main__":
    unittest.main()
