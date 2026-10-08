import unittest
from datetime import date
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app import main
from app.embedder import EmbeddingProviderError
from app.persistence import PersistenceError
from app.retrieval_repository import RetrievalIndexConfigurationError, RetrievedChunk
from app.retriever import VectorRetrievalResult
from app.schemas import RetrievalQueryRequest


class RetrievalQueryRouteTests(unittest.TestCase):
    def setUp(self):
        self.payload = RetrievalQueryRequest(
            question="I forgot my password and cannot log in.",
            top_k=2,
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

    def test_route_returns_raw_distance_and_source_version_metadata(self):
        query_retriever = Mock()
        query_retriever.retrieve.return_value = VectorRetrievalResult(
            hits=(self.hit,)
        )

        with patch.object(main, "retrieval_query_retriever", query_retriever):
            response = main.query_retrieval(self.payload)

        query_retriever.retrieve.assert_called_once_with(
            self.payload.question,
            top_k=2,
        )
        body = response.model_dump(mode="json")
        self.assertNotIn("retrieval_confidence", body)
        self.assertEqual(body["hits"][0]["cosine_distance"], 0.18)
        self.assertEqual(body["hits"][0]["policy_version"], "v1")
        self.assertEqual(body["hits"][0]["access_scope"], "internal")
        self.assertEqual(body["hits"][0]["chunk_id"], str(self.hit.chunk_id))

    def test_embedding_failure_maps_to_bad_gateway(self):
        query_retriever = Mock()
        query_retriever.retrieve.side_effect = EmbeddingProviderError("Ollama unavailable")

        with patch.object(main, "retrieval_query_retriever", query_retriever):
            with self.assertRaises(HTTPException) as raised:
                main.query_retrieval(self.payload)

        self.assertEqual(raised.exception.status_code, 502)

    def test_index_configuration_and_database_failures_map_to_service_unavailable(self):
        for error in (
            RetrievalIndexConfigurationError("digest mismatch"),
            PersistenceError("database unavailable"),
        ):
            with self.subTest(error=type(error).__name__):
                query_retriever = Mock()
                query_retriever.retrieve.side_effect = error

                with patch.object(main, "retrieval_query_retriever", query_retriever):
                    with self.assertRaises(HTTPException) as raised:
                        main.query_retrieval(self.payload)

                self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
