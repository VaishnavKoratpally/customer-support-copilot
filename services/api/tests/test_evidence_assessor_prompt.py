import unittest

from app.prompts import build_evidence_assessor_system_prompt


class EvidenceAssessorPromptTests(unittest.TestCase):
    def test_prompt_models_information_requests_separately_from_answers(self):
        prompt = build_evidence_assessor_system_prompt()

        self.assertIn(
            "return each as a concise label in requested_information",
            prompt,
        )
        self.assertIn(
            "requested_information='password-reset link expiry duration'",
            prompt,
        )
        self.assertIn(
            "finding=related_but_not_supported, answer=null",
            prompt,
        )
        self.assertIn(
            "Do not claim the link never expires or invent a duration",
            prompt,
        )
        self.assertIn(
            "requested_information='initial review duration'",
            prompt,
        )
        self.assertIn(
            "Leave supporting_facts empty",
            prompt,
        )
        self.assertIn(
            "be one contiguous substring copied verbatim",
            prompt,
        )
        self.assertIn(
            "use separate evidence entries for separate source spans",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
