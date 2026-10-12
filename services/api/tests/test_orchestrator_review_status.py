import unittest

from app.config import Settings
from app.llm_provider import StubLLMProvider
from app.orchestrator import StubRetrievalCopilotOrchestrator
from app.retriever import RetrievalResult
from app.schemas import Citation, SupportDraftRequest


class HighConfidenceRetriever:
    def retrieve(self, question: str) -> RetrievalResult:
        _ = question
        return RetrievalResult(
            citations=[
                Citation(
                    source_id="general-help-01",
                    title="General Help",
                    excerpt="Use account settings to update a profile.",
                )
            ],
            confidence=0.9,
        )


class OrchestratorReviewStatusTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = StubRetrievalCopilotOrchestrator(
            settings=Settings(
                MAIN_MODEL="stub",
                ESCALATION_MODEL="stub",
                RETRIEVAL_CONFIDENCE_THRESHOLD=0.55,
                ANSWER_CONFIDENCE_THRESHOLD=0.65,
            ),
            retriever=HighConfidenceRetriever(),
            llm_provider=StubLLMProvider(),
        )

    def test_high_risk_draft_starts_pending_review(self):
        result = self.orchestrator.draft_reply(
            SupportDraftRequest(question="I was charged twice for my plan.")
        )

        self.assertTrue(result.requires_human_review)
        self.assertEqual(result.review_status, "pending_review")

    def test_low_risk_confident_draft_does_not_require_review(self):
        result = self.orchestrator.draft_reply(
            SupportDraftRequest(
                question="Where can I update my profile information?"
            )
        )

        self.assertFalse(result.requires_human_review)
        self.assertEqual(result.review_status, "not_required")


if __name__ == "__main__":
    unittest.main()
