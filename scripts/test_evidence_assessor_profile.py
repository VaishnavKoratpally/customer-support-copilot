import unittest

from app.llm_provider import OllamaGenerationMetrics, OllamaGenerationResult
from evidence_assessor_profile import (
    CapturingStructuredGenerator,
    ProfileError,
    parse_cached_chunks,
    serialize_generation_metrics,
    summarize_model_residency,
)


class FakeProvider:
    def __init__(self):
        self.call_count = 0

    def generate_structured_with_metrics(self, **kwargs):
        self.call_count += 1
        return OllamaGenerationResult(
            text='{"status":"partial"}',
            metrics=OllamaGenerationMetrics(
                total_duration_ns=8_000_000_000,
                load_duration_ns=1_000_000_000,
                prompt_eval_count=120,
                prompt_eval_duration_ns=2_000_000_000,
                eval_count=50,
                eval_duration_ns=5_000_000_000,
                done_reason="stop",
            ),
        )


class EvidenceAssessorProfileTests(unittest.TestCase):
    def test_residency_reports_cold_when_model_is_not_loaded(self):
        residency = summarize_model_residency([], model_name="qwen3:4b")

        self.assertFalse(residency["loaded"])
        self.assertIsNone(residency["size_vram_bytes"])

    def test_residency_estimates_non_vram_model_memory(self):
        residency = summarize_model_residency(
            [
                {
                    "name": "qwen3:4b",
                    "size_bytes": 10_000,
                    "size_vram_bytes": 7_500,
                    "context_length": 4096,
                    "expires_at": "later",
                }
            ],
            model_name="qwen3:4b",
        )

        self.assertTrue(residency["loaded"])
        self.assertEqual(residency["estimated_non_vram_bytes"], 2_500)
        self.assertEqual(residency["vram_to_model_size_ratio"], 0.75)

    def test_cached_chunk_text_is_parsed_as_retrieved_evidence(self):
        chunks = parse_cached_chunks(
            [
                {
                    "chunk_id": "a4f34b41-154e-5177-8a97-d38ab453bcb5",
                    "source_id": "support-sla-02",
                    "title": "Synthetic Billing Dispute Review SLA",
                    "policy_version": "week3-synthetic-v1",
                    "effective_date": "2026-10-06",
                    "access_scope": "internal",
                    "chunk_index": 2,
                    "section_path": "Billing dispute resolution",
                    "text": "Billing disputes require human review.",
                    "cosine_distance": 0.33,
                }
            ],
            case_id="bi-005",
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "Billing disputes require human review.")
        self.assertEqual(chunks[0].source_id, "support-sla-02")

    def test_capturing_generator_rejects_a_second_generation_call(self):
        provider = FakeProvider()
        generator = CapturingStructuredGenerator(provider)
        arguments = {
            "model_name": "qwen3:4b",
            "system_prompt": "System",
            "user_prompt": "User",
            "response_schema": {"type": "object"},
        }

        self.assertEqual(generator.generate_structured(**arguments), '{"status":"partial"}')
        with self.assertRaisesRegex(ProfileError, "only one generation request"):
            generator.generate_structured(**arguments)
        self.assertEqual(provider.call_count, 1)

    def test_metrics_are_reported_in_seconds_and_tokens_per_second(self):
        metrics = serialize_generation_metrics(
            OllamaGenerationResult(
                text='{"status":"partial"}',
                metrics=OllamaGenerationMetrics(
                    total_duration_ns=8_000_000_000,
                    load_duration_ns=1_000_000_000,
                    prompt_eval_count=120,
                    prompt_eval_duration_ns=2_000_000_000,
                    eval_count=50,
                    eval_duration_ns=5_000_000_000,
                    done_reason="stop",
                ),
            ),
            wall_seconds=8.2,
            call_count=1,
        )

        self.assertEqual(metrics["model_load_seconds"], 1.0)
        self.assertEqual(metrics["prompt_evaluation_seconds"], 2.0)
        self.assertEqual(metrics["generation_seconds"], 5.0)
        self.assertEqual(metrics["generated_tokens_per_second"], 10.0)


if __name__ == "__main__":
    unittest.main()
