import unittest
from datetime import date
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app import main
from app.embedder import EmbeddingProviderError
from app.orchestrator import PreviewOnlyDraftOrchestrator
from app.persistence import PersistenceError
from app.retrieval_repository import RetrievalIndexConfigurationError, RetrievedChunk
from app.retriever import VectorRetrievalResult
from app.schemas import SupportDraftRequest


class FakeRetriever:
    def __init__(self, hits: tuple[RetrievedChunk, ...]) -> None:
        self.hits = hits
        self.received_question: str | None = None
        self.received_top_k: int | None = None

    def retrieve(self, question: str, *, top_k: int = 3) -> VectorRetrievalResult:
        self.received_question = question
        self.received_top_k = top_k
        return VectorRetrievalResult(hits=self.hits)


class SupportDraftPreviewTests(unittest.TestCase):
    def setUp(self):
        self.payload = SupportDraftRequest(
            question="I cannot sign in to my account."
        )
        self.hit = RetrievedChunk(
            chunk_id=uuid4(),
            source_id="account-recovery-01",
            title="Account recovery policy",
            policy_version="v1",
            effective_date=date(2026, 10, 6),
            access_scope="internal",
            chunk_index=0,
            section_path="Account recovery",
            text="Use password recovery from the sign-in page.",
            cosine_distance=0.18,
        )

    def test_preview_returns_retrieved_chunk_provenance_without_claiming_confidence(self):
        retriever = FakeRetriever((self.hit,))
        orchestrator = PreviewOnlyDraftOrchestrator(retriever=retriever)

        response = orchestrator.draft_reply(self.payload)

        self.assertEqual(retriever.received_question, self.payload.question)
        self.assertEqual(retriever.received_top_k, 3)
        self.assertEqual(response.draft_mode, "preview_only")
        self.assertEqual(response.model_used, "none_preview_only")
        self.assertTrue(response.requires_human_review)
        self.assertEqual(response.review_status, "pending_review")
        self.assertIsNone(response.retrieval_confidence)
        self.assertIsNone(response.answer_confidence)
        self.assertIn("No customer response was generated.", response.draft)
        self.assertEqual(response.citation_source_ids, ["account-recovery-01"])
        self.assertTrue(response.citation_contract_passed)
        self.assertEqual(len(response.citations), 1)
        citation = response.citations[0]
        self.assertEqual(citation.chunk_id, self.hit.chunk_id)
        self.assertEqual(citation.policy_version, "v1")
        self.assertEqual(citation.effective_date, date(2026, 10, 6))
        self.assertEqual(citation.access_scope, "internal")
        self.assertEqual(citation.chunk_index, 0)
        self.assertEqual(citation.section_path, "Account recovery")
        self.assertEqual(citation.excerpt, self.hit.text)
        self.assertEqual(citation.cosine_distance, 0.18)
        self.assertIn("evidence_assessment_not_validated", response.review_triggers)

    def test_empty_retrieval_returns_explicit_abstention_and_pending_review(self):
        orchestrator = PreviewOnlyDraftOrchestrator(retriever=FakeRetriever(()))

        response = orchestrator.draft_reply(self.payload)

        self.assertIn("no eligible support evidence was retrieved", response.draft)
        self.assertEqual(response.citations, [])
        self.assertEqual(response.citation_source_ids, [])
        self.assertFalse(response.citation_contract_passed)
        self.assertTrue(response.requires_human_review)
        self.assertEqual(response.review_status, "pending_review")
        self.assertEqual(response.escalation_reason, "no_retrieved_evidence")
        self.assertIn("no_retrieved_evidence", response.review_triggers)

    def test_draft_endpoint_persists_the_preview_and_real_citations(self):
        orchestrator = PreviewOnlyDraftOrchestrator(
            retriever=FakeRetriever((self.hit,))
        )
        repository = Mock()

        with (
            patch.object(main, "orchestrator", orchestrator),
            patch.object(main, "support_repository", repository),
        ):
            response = main.draft_support_reply(self.payload)

        repository.save_support_draft.assert_called_once_with(
            draft_request=self.payload,
            draft_response=response,
        )
        persisted_response = repository.save_support_draft.call_args.kwargs[
            "draft_response"
        ]
        self.assertEqual(persisted_response.draft_mode, "preview_only")
        self.assertIsNone(persisted_response.retrieval_confidence)
        self.assertEqual(persisted_response.citations[0].chunk_id, self.hit.chunk_id)

    def test_draft_endpoint_maps_embedding_and_index_failures_without_fallback(self):
        failures = (
            (EmbeddingProviderError("Ollama unavailable"), 502),
            (RetrievalIndexConfigurationError("embedding digest mismatch"), 503),
            (PersistenceError("database unavailable"), 503),
        )
        for error, expected_status in failures:
            with self.subTest(error=type(error).__name__):
                orchestrator = Mock()
                orchestrator.draft_reply.side_effect = error
                repository = Mock()
                with (
                    patch.object(main, "orchestrator", orchestrator),
                    patch.object(main, "support_repository", repository),
                ):
                    with self.assertRaises(HTTPException) as raised:
                        main.draft_support_reply(self.payload)

                self.assertEqual(raised.exception.status_code, expected_status)
                repository.save_support_draft.assert_not_called()


if __name__ == "__main__":
    unittest.main()
