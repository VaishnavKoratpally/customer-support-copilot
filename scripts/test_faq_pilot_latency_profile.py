import unittest

from profile_faq_pilot_latency import (
    LatencyProfileError,
    capture_error_requires_stop,
    extract_profile_metrics,
    require_ollama_unloaded,
    review_first_violation,
    schedule_warm_cases,
    select_cold_case,
    summarize_latencies,
    summarize_profile,
)


class FaqPilotLatencyProfileTests(unittest.TestCase):
    def test_selects_cold_case_from_frozen_development_cases(self):
        cases = [
            {"case_id": "faq-dev-001"},
            {"case_id": "faq-dev-003"},
        ]

        self.assertEqual(select_cold_case(cases), cases[1])

    def test_warm_schedule_cycles_through_only_the_supplied_development_cases(self):
        cases = [{"case_id": f"faq-dev-{index:03d}"} for index in range(1, 9)]

        warm_cases = schedule_warm_cases(cases)

        self.assertEqual(len(warm_cases), 20)
        self.assertEqual(
            [case["case_id"] for case in warm_cases[:10]],
            [
                "faq-dev-001",
                "faq-dev-002",
                "faq-dev-003",
                "faq-dev-004",
                "faq-dev-005",
                "faq-dev-006",
                "faq-dev-007",
                "faq-dev-008",
                "faq-dev-001",
                "faq-dev-002",
            ],
        )

    def test_warm_schedule_rejects_fewer_than_twenty_requests(self):
        with self.assertRaisesRegex(LatencyProfileError, "at least 20"):
            schedule_warm_cases([{"case_id": "faq-dev-001"}], request_count=19)

    def test_cold_preflight_rejects_any_resident_ollama_model(self):
        with self.assertRaisesRegex(LatencyProfileError, "Restart the Ollama service"):
            require_ollama_unloaded([{"name": "qwen3:4b"}])

    def test_http_server_errors_are_recorded_but_configuration_errors_stop_the_run(self):
        self.assertIsNone(
            capture_error_requires_stop(
                {
                    "capture_status": "error",
                    "error": "Support draft API returned HTTP 502 Bad Gateway",
                }
            )
        )
        self.assertIn(
            "non-server API error",
            capture_error_requires_stop(
                {
                    "capture_status": "error",
                    "error": "Support draft quality evaluation requires generated mode",
                }
            ),
        )

    def test_latency_percentiles_include_error_request_wall_time(self):
        summary = summarize_latencies(
            [
                {"capture_status": "captured", "client_latency_ms": 100},
                {"capture_status": "error", "client_latency_ms": 200},
            ]
        )

        self.assertEqual(summary["attempts"], 2)
        self.assertEqual(summary["captured"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["p50_client_latency_ms"], 150)
        self.assertEqual(summary["p95_client_latency_ms"], 195)

    def test_missing_latency_samples_are_not_marked_as_target_misses(self):
        summary = summarize_profile([], ollama_processes_before=[])

        self.assertIsNone(summary["warm"]["targets"]["p50_met"])
        self.assertIsNone(summary["warm"]["targets"]["p95_met"])
        self.assertIsNone(summary["combined"]["targets"]["p50_met"])
        self.assertIsNone(summary["combined"]["targets"]["p95_met"])

    def test_extracts_component_times_tokens_and_model_settings(self):
        response = {
            "intent": "billing_faq",
            "risk_level": "low",
            "review_status": "pending_review",
            "requires_human_review": True,
            "generation_metadata": {
                "outcome": "generated",
                "automation_enabled": False,
                "automation_eligibility": {"eligible_candidate": True},
                "retrieved_chunk_count": 2,
                "retrieval_elapsed_seconds": 0.12,
                "assessor_elapsed_seconds": 1.5,
                "assessor_model": "qwen3:4b",
                "assessor_max_output_tokens": 1024,
                "assessor_system_prompt_sha256": "a" * 64,
                "assessor_user_prompt_sha256": "b" * 64,
                "assessor_schema_sha256": "c" * 64,
                "assessor_metrics": {
                    "prompt_eval_count": 120,
                    "eval_count": 32,
                    "load_duration_ns": 4_000_000,
                    "prompt_eval_duration_ns": 500_000_000,
                    "eval_duration_ns": 900_000_000,
                    "total_duration_ns": 1_500_000_000,
                    "done_reason": "stop",
                },
                "generator_elapsed_seconds": 0.7,
                "generator_model": "qwen3:4b",
                "generator_max_output_tokens": 256,
                "generator_system_prompt_sha256": "d" * 64,
                "generator_user_prompt_sha256": "e" * 64,
                "generator_schema_sha256": "f" * 64,
                "generator_metrics": None,
            },
        }

        metrics = extract_profile_metrics(response)

        self.assertEqual(metrics["retrieval_elapsed_seconds"], 0.12)
        self.assertEqual(metrics["assessor_metrics"]["prompt_tokens"], 120)
        self.assertEqual(metrics["assessor_metrics"]["generated_tokens"], 32)
        self.assertEqual(metrics["assessor_max_output_tokens"], 1024)
        self.assertEqual(metrics["generator_max_output_tokens"], 256)

    def test_response_must_remain_pending_review_with_automation_off(self):
        response = {
            "review_status": "pending_review",
            "requires_human_review": True,
            "generation_metadata": {"automation_enabled": False},
        }

        self.assertIsNone(review_first_violation(response))

        response["generation_metadata"]["automation_enabled"] = True
        self.assertIn("disabled", review_first_violation(response))

    def test_response_without_retrieval_timing_is_not_profile_valid(self):
        response = {
            "generation_metadata": {
                "outcome": "generated",
                "automation_enabled": False,
            }
        }

        with self.assertRaisesRegex(LatencyProfileError, "no retrieval timing"):
            extract_profile_metrics(response)


if __name__ == "__main__":
    unittest.main()
