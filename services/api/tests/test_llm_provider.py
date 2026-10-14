import json
import unittest
from unittest.mock import patch

from app.llm_provider import OllamaLLMProvider, OllamaProviderError


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._body


class OllamaLLMProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = OllamaLLMProvider(
            base_url="http://ollama:11434",
            timeout_seconds=30,
        )

    def test_generate_structured_sends_schema_and_returns_response_text(self):
        schema = {
            "type": "object",
            "properties": {"supported": {"type": "boolean"}},
            "required": ["supported"],
        }
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"response": '{"supported": true}'}),
        ) as urlopen:
            result = self.provider.generate_structured(
                model_name="qwen3:4b",
                system_prompt="Assess evidence.",
                user_prompt="Is the claim supported?",
                response_schema=schema,
            )

        self.assertEqual(result, '{"supported": true}')
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://ollama:11434/api/generate")
        self.assertEqual(request_payload["format"], schema)
        self.assertFalse(request_payload["stream"])
        self.assertFalse(request_payload["think"])
        self.assertEqual(request_payload["options"]["temperature"], 0)
        self.assertEqual(request_payload["options"]["num_predict"], 1024)

    def test_generate_structured_with_metrics_captures_ollama_timings(self):
        response = {
            "response": '{"supported": true}',
            "total_duration": 12_000_000_000,
            "load_duration": 2_000_000_000,
            "prompt_eval_count": 140,
            "prompt_eval_duration": 3_000_000_000,
            "eval_count": 35,
            "eval_duration": 7_000_000_000,
            "done_reason": "stop",
            "done": True,
        }
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ):
            result = self.provider.generate_structured_with_metrics(
                model_name="qwen3:4b",
                system_prompt="Assess evidence.",
                user_prompt="Is the claim supported?",
                response_schema={"type": "object"},
            )

        self.assertEqual(result.text, '{"supported": true}')
        self.assertEqual(result.metrics.total_duration_ns, 12_000_000_000)
        self.assertEqual(result.metrics.load_duration_ns, 2_000_000_000)
        self.assertEqual(result.metrics.prompt_eval_count, 140)
        self.assertEqual(result.metrics.prompt_eval_duration_ns, 3_000_000_000)
        self.assertEqual(result.metrics.eval_count, 35)
        self.assertEqual(result.metrics.eval_duration_ns, 7_000_000_000)
        self.assertEqual(result.metrics.done_reason, "stop")
        self.assertTrue(result.metrics.done)

    def test_generate_structured_with_metrics_honors_output_budget(self):
        response = {
            "response": '{"draft": "Only workspace owners can download invoices."}',
            "eval_count": 16,
            "done_reason": "stop",
            "done": True,
        }
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as urlopen:
            result = self.provider.generate_structured_with_metrics(
                model_name="qwen3:4b",
                system_prompt="Write from evidence.",
                user_prompt="Question and validated facts.",
                response_schema={
                    "type": "object",
                    "properties": {"draft": {"type": "string"}},
                    "required": ["draft"],
                    "additionalProperties": False,
                },
                max_output_tokens=256,
            )

        self.assertEqual(result.text, response["response"])
        request_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_payload["model"], "qwen3:4b")
        self.assertEqual(request_payload["options"]["temperature"], 0)
        self.assertEqual(request_payload["options"]["num_predict"], 256)
        self.assertFalse(request_payload["stream"])
        self.assertFalse(request_payload["think"])
        self.assertTrue(result.metrics.done)
        self.assertEqual(result.metrics.done_reason, "stop")

    def test_generate_structured_with_metrics_rejects_invalid_done_flag(self):
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(
                {"response": '{"draft": "Draft"}', "done": "true"}
            ),
        ):
            with self.assertRaisesRegex(
                OllamaProviderError,
                "done.*boolean",
            ):
                self.provider.generate_structured_with_metrics(
                    model_name="qwen3:4b",
                    system_prompt="Write from evidence.",
                    user_prompt="Question and validated facts.",
                    response_schema={"type": "object"},
                    max_output_tokens=256,
                )

    def test_generate_structured_with_metrics_rejects_invalid_counts(self):
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(
                {"response": '{"supported": true}', "eval_count": "35"}
            ),
        ):
            with self.assertRaisesRegex(
                OllamaProviderError,
                "eval_count.*non-negative integer",
            ):
                self.provider.generate_structured_with_metrics(
                    model_name="qwen3:4b",
                    system_prompt="Assess evidence.",
                    user_prompt="Is the claim supported?",
                    response_schema={"type": "object"},
                )

    def test_draft_response_keeps_existing_generation_parameters(self):
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"response": "Draft text"}),
        ) as urlopen:
            result = self.provider.draft_response(
                question="Question",
                intent="billing",
                model_name="qwen3:14b",
                system_prompt="System",
                user_prompt="User",
            )

        self.assertEqual(result, "Draft text")
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_payload["options"]["num_predict"], 64)
        self.assertNotIn("format", request_payload)

    def test_generate_structured_rejects_non_text_response(self):
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"response": {"unexpected": "object"}}),
        ):
            with self.assertRaisesRegex(
                OllamaProviderError,
                "textual response field",
            ):
                self.provider.generate_structured(
                    model_name="qwen3:4b",
                    system_prompt="Assess evidence.",
                    user_prompt="Question",
                    response_schema={"type": "object"},
                )

    def test_generate_structured_surfaces_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            with self.assertRaisesRegex(
                OllamaProviderError,
                "request timed out",
            ):
                self.provider.generate_structured(
                    model_name="qwen3:4b",
                    system_prompt="Assess evidence.",
                    user_prompt="Question",
                    response_schema={"type": "object"},
                )


if __name__ == "__main__":
    unittest.main()
