import unittest
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4
from unittest.mock import Mock, patch

from app.evidence_assessment import EvidenceAssessmentDecision
from app.retrieval_repository import RetrievedChunk
from eval_utils import DatasetError, load_cases
from evidence_assessor_pilot import (
    REQUIRED_FIELDS,
    evaluate_case,
    gold_evidence_retrieval_metrics,
    is_false_sufficient_status,
    load_assessor_gold,
    parse_retrieval_fixture_chunks,
    summarize_results,
    validate_assessor_gold,
    validate_case,
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

    def test_heldout_gold_matches_dataset_and_covers_each_assessor_status(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cases = load_cases(
            repo_root / "docs" / "evals" / "evidence-assessor-heldout-v1.jsonl",
            REQUIRED_FIELDS,
        )
        for case in cases:
            validate_case(case)
        gold_by_id = load_assessor_gold(
            repo_root / "docs" / "evals" / "evidence-assessor-heldout-gold-v1.jsonl",
            cases,
        )

        self.assertEqual(len(cases), 8)
        self.assertEqual(
            {case["evidence_sufficiency"] for case in cases},
            {
                "sufficient",
                "partial",
                "insufficient",
                "none",
                "clarification_needed",
                "conflicting",
            },
        )
        fixture_cases = [case for case in cases if "retrieval_fixture_hits" in case]
        self.assertEqual([case["id"] for case in fixture_cases], [
            "heldout-conflicting-review-duration",
        ])
        self.assertEqual(
            gold_by_id["heldout-conflicting-review-duration"][
                "requested_information"
            ][0]["finding"],
            "conflicting",
        )

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


class EvidenceAssessorFixtureTests(unittest.TestCase):
    def test_fixture_chunks_bypass_api_retrieval_and_reach_the_assessor(self) -> None:
        case = make_conflicting_fixture_case()
        validate_case(case)
        chunks = parse_retrieval_fixture_chunks(case)
        assessor_gold = make_conflicting_fixture_gold()
        assessor = Mock()
        assessor.assess.return_value = EvidenceAssessmentDecision(
            status="conflicting",
            action="abstain_and_escalate_conflict",
            requested_information=[],
            supporting_facts=[],
        )

        with patch("evidence_assessor_pilot.call_retrieval") as call_retrieval:
            result = evaluate_case(
                case=case,
                assessor_gold=assessor_gold,
                assessor=assessor,
                api_base_url="http://unused",
                retrieval_timeout_seconds=1,
            )

        call_retrieval.assert_not_called()
        assessor.assess.assert_called_once_with(
            question=case["question"],
            retrieved_chunks=chunks,
        )
        self.assertEqual(result["retrieval"]["mode"], "fixture")
        self.assertIsNone(result["retrieval"]["elapsed_seconds"])
        self.assertIsNone(result["latency"]["retrieval_seconds"])
        self.assertTrue(result["checks"]["gold_evidence_retrieved"])

    def test_fixture_sources_must_include_expected_sources(self) -> None:
        case = make_conflicting_fixture_case()
        case["expected_retrieval_source_ids"].append("missing-policy")

        with self.assertRaisesRegex(DatasetError, "missing expected sources"):
            validate_case(case)

    def test_summary_excludes_fixture_chunks_from_retrieval_metrics(self) -> None:
        api_result = {
            "expected": {"evidence_sufficiency": "sufficient"},
            "checks": {
                "status_matches_expected": True,
                "false_sufficient": False,
            },
            "retrieval": {
                "mode": "api",
                "source_recall_at_k": 0.5,
                "assessor_gold_evidence": {
                    "expected_quote_count": 2,
                    "retrieved_quote_count": 1,
                },
            },
            "latency": {
                "retrieval_seconds": 2.0,
                "assessment_seconds": 4.0,
            },
        }
        fixture_result = {
            "expected": {"evidence_sufficiency": "conflicting"},
            "checks": {
                "status_matches_expected": True,
                "false_sufficient": False,
            },
            "retrieval": {
                "mode": "fixture",
                "source_recall_at_k": 1.0,
                "assessor_gold_evidence": {
                    "expected_quote_count": 2,
                    "retrieved_quote_count": 2,
                },
            },
            "latency": {
                "retrieval_seconds": None,
                "assessment_seconds": 6.0,
            },
        }

        summary = summarize_results([api_result, fixture_result])

        self.assertEqual(summary["status_matches"], 2)
        self.assertEqual(summary["mean_source_recall_at_k"], 0.5)
        self.assertEqual(summary["expected_gold_quote_count"], 2)
        self.assertEqual(summary["retrieved_gold_quote_count"], 1)
        self.assertEqual(summary["mean_retrieval_seconds"], 2.0)
        self.assertEqual(summary["mean_assessment_seconds"], 5.0)


def make_conflicting_fixture_case() -> dict[str, Any]:
    return {
        "id": "heldout-conflicting-review-window",
        "question": "How long does the initial review of a reported card dispute take?",
        "top_k": 2,
        "expected_retrieval_source_ids": [
            "heldout-review-policy-a",
            "heldout-review-policy-b",
        ],
        "evidence_sufficiency": "conflicting",
        "expected_action": "abstain_and_escalate_conflict",
        "supporting_facts": [],
        "claims_to_avoid": [
            "State either review duration as the definitive policy.",
        ],
        "expected_human_review": True,
        "retrieval_fixture_hits": [
            {
                "chunk_id": "b4400000-0000-4000-8000-000000000001",
                "source_id": "heldout-review-policy-a",
                "title": "Evaluation-only Review Policy A",
                "policy_version": "heldout-fixture-v1",
                "effective_date": "2026-10-13",
                "access_scope": "internal",
                "chunk_index": 0,
                "section_path": "Card dispute review",
                "excerpt": (
                    "For a reported card dispute, the initial review is "
                    "completed within 1 business day."
                ),
                "cosine_distance": 0.1,
            },
            {
                "chunk_id": "b4400000-0000-4000-8000-000000000002",
                "source_id": "heldout-review-policy-b",
                "title": "Evaluation-only Review Policy B",
                "policy_version": "heldout-fixture-v1",
                "effective_date": "2026-10-13",
                "access_scope": "internal",
                "chunk_index": 1,
                "section_path": "Card dispute review",
                "excerpt": (
                    "For a reported card dispute, the initial review is "
                    "completed within 3 business days."
                ),
                "cosine_distance": 0.2,
            },
        ],
    }


def make_conflicting_fixture_gold() -> dict[str, Any]:
    return {
        "requested_information": [
            {
                "id": "initial-review-duration",
                "requested_information": "initial review duration for a card dispute",
                "finding": "conflicting",
                "answer": None,
                "evidence": [
                    {
                        "source_id": "heldout-review-policy-a",
                        "section_path": "Card dispute review",
                        "quote": (
                            "For a reported card dispute, the initial review is "
                            "completed within 1 business day."
                        ),
                    },
                    {
                        "source_id": "heldout-review-policy-b",
                        "section_path": "Card dispute review",
                        "quote": (
                            "For a reported card dispute, the initial review is "
                            "completed within 3 business days."
                        ),
                    },
                ],
            }
        ],
        "supporting_facts": [],
        "clarification_topics": [],
    }


if __name__ == "__main__":
    unittest.main()
