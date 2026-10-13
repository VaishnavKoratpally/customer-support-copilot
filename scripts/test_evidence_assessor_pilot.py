import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4

from app.retrieval_repository import RetrievedChunk
from eval_utils import DatasetError, load_cases
from evidence_assessor_pilot import (
    REQUIRED_FIELDS,
    gold_evidence_retrieval_metrics,
    is_false_sufficient_status,
    load_assessor_gold,
    validate_assessor_gold,
)


class EvidenceAssessorGoldTests(unittest.TestCase):
    def test_checked_in_gold_matches_all_fixed_cases_and_aggregate_statuses(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cases = load_cases(
            repo_root / "docs" / "evals" / "rag-week3-v1.jsonl",
            REQUIRED_FIELDS,
        )
        gold_by_id = load_assessor_gold(
            repo_root / "docs" / "evals" / "evidence-assessor-gold-v1.jsonl",
            cases,
        )

        self.assertEqual(len(gold_by_id), 12)
        self.assertEqual(
            gold_by_id["ar-002-reset-link-expiry-unsupported"][
                "requested_information"
            ][0]["finding"],
            "related_but_not_supported",
        )
        credit_case = gold_by_id["bi-005-credit-posting-date-partial-evidence"]
        self.assertEqual(
            credit_case["requested_information"][0]["finding"],
            "related_but_not_supported",
        )
        self.assertEqual(len(credit_case["supporting_facts"]), 3)

    def test_gold_status_must_match_its_atomic_labels(self) -> None:
        assessor_gold = {
            "requested_information": [
                {
                    "id": "credit-posting-date",
                    "requested_information": "credit-posting date",
                    "finding": "related_but_not_supported",
                    "answer": None,
                    "evidence": [
                        {
                            "source_id": "support-sla-02",
                            "section_path": "Billing dispute resolution",
                            "quote": "The review window is not a guaranteed credit-posting date.",
                        }
                    ],
                }
            ],
            "supporting_facts": [],
            "clarification_topics": [],
        }

        with self.assertRaisesRegex(DatasetError, "derives 'insufficient'"):
            validate_assessor_gold(
                case_id="bi-005",
                expected_status="partial",
                expected_source_ids={"support-sla-02"},
                assessor_gold=assessor_gold,
            )

    def test_gold_quote_retrieval_requires_matching_source_section_and_text(self) -> None:
        assessor_gold = {
            "requested_information": [
                {
                    "evidence": [
                        {
                            "source_id": "support-sla-02",
                            "section_path": "Billing dispute resolution",
                            "quote": "Review timing is not a guaranteed credit-posting date.",
                        }
                    ]
                }
            ],
            "supporting_facts": [],
        }
        chunk = RetrievedChunk(
            chunk_id=uuid4(),
            source_id="support-sla-02",
            title="Billing support SLA",
            policy_version="v1",
            effective_date=date(2026, 1, 1),
            access_scope="customer_support",
            chunk_index=0,
            section_path="Billing dispute resolution",
            text="Review timing is not a guaranteed credit-posting date.",
            cosine_distance=0.1,
        )

        metrics = gold_evidence_retrieval_metrics(
            assessor_gold=assessor_gold,
            chunks=(chunk,),
        )
        self.assertTrue(metrics["all_expected_quotes_retrieved"])
        self.assertEqual(metrics["retrieved_quote_count"], 1)

        wrong_section = RetrievedChunk(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            title=chunk.title,
            policy_version=chunk.policy_version,
            effective_date=chunk.effective_date,
            access_scope=chunk.access_scope,
            chunk_index=chunk.chunk_index,
            section_path="Different section",
            text=chunk.text,
            cosine_distance=chunk.cosine_distance,
        )
        missing_metrics = gold_evidence_retrieval_metrics(
            assessor_gold=assessor_gold,
            chunks=(wrong_section,),
        )
        self.assertFalse(missing_metrics["all_expected_quotes_retrieved"])
        self.assertEqual(missing_metrics["retrieved_quote_count"], 0)

    def test_false_sufficient_metric_only_flags_non_sufficient_gold(self) -> None:
        self.assertTrue(
            is_false_sufficient_status(
                actual_status="sufficient",
                expected_status="insufficient",
            )
        )
        self.assertFalse(
            is_false_sufficient_status(
                actual_status="sufficient",
                expected_status="sufficient",
            )
        )
        self.assertFalse(
            is_false_sufficient_status(
                actual_status="none",
                expected_status="insufficient",
            )
        )


if __name__ == "__main__":
    unittest.main()
