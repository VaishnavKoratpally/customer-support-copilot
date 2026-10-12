import json
import unittest
from unittest.mock import patch

from eval_utils import EvaluationAPIError, call_support_draft


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._body


class EvaluationAPITests(unittest.TestCase):
    def call_api(self, body: dict) -> dict:
        with patch("eval_utils.urlopen", return_value=FakeResponse(body)):
            return call_support_draft(
                api_base_url="http://localhost:8000",
                question="How do I update my account?",
                timeout_seconds=1,
            )

    def test_rejects_preview_only_response_before_quality_scoring(self):
        with self.assertRaisesRegex(
            EvaluationAPIError,
            "requires generated mode; received draft_mode='preview_only'",
        ):
            self.call_api({"draft_mode": "preview_only", "draft": "No response."})

    def test_accepts_generated_response_for_existing_contract_checks(self):
        response = {
            "draft_mode": "generated",
            "draft": "Use account settings to update your profile.",
            "citation_source_ids": ["account-settings-01"],
            "citation_contract_passed": True,
        }

        self.assertEqual(self.call_api(response), response)


if __name__ == "__main__":
    unittest.main()
