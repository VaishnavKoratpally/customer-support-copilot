import unittest
from pathlib import Path
from unittest.mock import patch

from capture_faq_pilot_eval import (
    capture_case,
    capture_cases,
    load_pilot_cases,
)
from eval_utils import EvaluationAPIError


class FAQPilotCaptureTests(unittest.TestCase):
    def test_development_cases_match_the_frozen_contract(self):
        repo_root = Path(__file__).resolve().parents[1]

        contract_id, dataset, cases, canonical_hash = load_pilot_cases(
            repo_root,
            "development",
        )

        self.assertEqual(contract_id, "faq-pilot-v1")
        self.assertEqual(dataset.name, "faq-pilot-development-v1.jsonl")
        self.assertEqual(len(cases), 8)
        self.assertEqual(
            canonical_hash,
            "b4b60df295648facc268ef8cd5efc298389cb8ffbdc74781b0296adc51be22a9",
        )

    def test_capture_records_full_response_and_client_latency(self):
        case = {
            "case_id": "faq-dev-001",
            "question": "How do I download an issued invoice?",
        }
        response = {
            "trace_id": "trace-1",
            "draft_mode": "generated",
            "intent": "general_support",
            "risk_level": "low",
            "model_used": "assessor=qwen3:4b;generator=qwen3:4b",
            "draft": "A generated draft.",
            "citations": [],
            "retrieval_confidence": None,
            "answer_confidence": None,
            "requires_human_review": True,
            "review_status": "pending_review",
            "escalation_reason": "generated_pilot_review_first",
            "citation_source_ids": [],
            "citation_contract_passed": False,
            "review_triggers": ["generated_pilot_review_first"],
            "evidence_assessment": None,
            "generation_metadata": {
                "outcome": "generated",
                "generation_completion_verified": True,
                "automation_enabled": False,
                "final_response_checks": {},
                "automation_eligibility": {},
            },
        }
        with patch(
            "capture_faq_pilot_eval.call_support_draft",
            return_value=response,
        ):
            result = capture_case(
                case,
                api_base_url="http://localhost:8000",
                timeout_seconds=10,
            )

        self.assertEqual(result["capture_status"], "captured")
        self.assertEqual(result["response"], response)
        self.assertEqual(result["http_status_code"], 200)
        self.assertIsInstance(result["client_latency_ms"], float)

    def test_capture_records_api_errors_and_continues_to_later_cases(self):
        cases = [
            {
                "case_id": "faq-dev-001",
                "question": "How do I download an issued invoice?",
            },
            {
                "case_id": "faq-dev-002",
                "question": "Which workspace roles can download invoices?",
            },
        ]
        with patch(
            "capture_faq_pilot_eval.call_support_draft",
            side_effect=[
                EvaluationAPIError("HTTP 502"),
                {
                    "trace_id": "trace-2",
                    "draft_mode": "generated",
                    "intent": "general_support",
                    "risk_level": "low",
                    "model_used": "assessor=qwen3:4b",
                    "draft": "A generated draft.",
                    "citations": [],
                    "retrieval_confidence": None,
                    "answer_confidence": None,
                    "requires_human_review": True,
                    "review_status": "pending_review",
                    "escalation_reason": "generated_pilot_review_first",
                    "citation_source_ids": [],
                    "citation_contract_passed": False,
                    "review_triggers": ["generated_pilot_review_first"],
                    "evidence_assessment": None,
                    "generation_metadata": {
                        "outcome": "generated",
                        "generation_completion_verified": True,
                        "automation_enabled": False,
                        "final_response_checks": {},
                        "automation_eligibility": {},
                    },
                },
            ],
        ):
            results = capture_cases(
                cases,
                api_base_url="http://localhost:8000",
                timeout_seconds=10,
            )

        self.assertEqual(
            [result["capture_status"] for result in results],
            ["error", "captured"],
        )
        self.assertEqual(results[0]["error"], "HTTP 502")
        self.assertEqual(results[1]["response"]["trace_id"], "trace-2")


if __name__ == "__main__":
    unittest.main()
