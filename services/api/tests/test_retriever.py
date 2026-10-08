import unittest
from datetime import date
from uuid import uuid4

from app.embedder import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    EmbeddingProviderError,
    VECTOR_DIMENSION,
)
from app.retrieval_repository import RetrievedChunk
from app.retriever import PgVectorRetriever


class FakeEmbeddingProvider:
    def __init__(self, batch: EmbeddingBatch) -> None:
        self.batch = batch
        self.received_texts: list[str] = []

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            model_name=self.batch.model_name,
            model_digest=self.batch.model_digest,
            dimension=self.batch.dimension,
        )

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        self.received_texts = texts
        return self.batch


class FakeRetrievalRepository:
    def __init__(self, hits: tuple[RetrievedChunk, ...]) -> None:
        self.hits = hits
        self.search_arguments: dict | None = None

    def search(self, **arguments) -> tuple[RetrievedChunk, ...]:
        self.search_arguments = arguments
        return self.hits


class PgVectorRetrieverTests(unittest.TestCase):
    def test_embeds_question_and_passes_vector_metadata_to_repository(self):
        query_vector = (0.125,) * VECTOR_DIMENSION
        model_info = EmbeddingModelInfo(
            model_name="qwen3-embedding:0.6b",
            model_digest="sha256:test-digest",
            dimension=VECTOR_DIMENSION,
        )
        embedder = FakeEmbeddingProvider(
            EmbeddingBatch(
                model_name=model_info.model_name,
                model_digest=model_info.model_digest,
                dimension=model_info.dimension,
                vectors=(query_vector,),
            )
        )
        hit = RetrievedChunk(
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
        repository = FakeRetrievalRepository((hit,))
        retriever = PgVectorRetriever(embedder=embedder, repository=repository)

        result = retriever.retrieve("I cannot sign in.", top_k=2)

        self.assertEqual(embedder.received_texts, ["I cannot sign in."])
        self.assertEqual(result.hits, (hit,))
        self.assertEqual(repository.search_arguments["query_vector"], query_vector)
        self.assertEqual(repository.search_arguments["embedding_model_info"], model_info)
        self.assertEqual(repository.search_arguments["top_k"], 2)

    def test_rejects_invalid_single_query_embedding(self):
        embedder = FakeEmbeddingProvider(
            EmbeddingBatch(
                model_name="qwen3-embedding:0.6b",
                model_digest="sha256:test-digest",
                dimension=VECTOR_DIMENSION,
                vectors=(),
            )
        )
        repository = FakeRetrievalRepository(())
        retriever = PgVectorRetriever(embedder=embedder, repository=repository)

        with self.assertRaisesRegex(EmbeddingProviderError, "0 vectors for one query"):
            retriever.retrieve("I cannot sign in.")

        self.assertIsNone(repository.search_arguments)

    def test_rejects_query_vector_dimension_mismatch(self):
        embedder = FakeEmbeddingProvider(
            EmbeddingBatch(
                model_name="qwen3-embedding:0.6b",
                model_digest="sha256:test-digest",
                dimension=VECTOR_DIMENSION,
                vectors=((0.1, 0.2),),
            )
        )
        repository = FakeRetrievalRepository(())
        retriever = PgVectorRetriever(embedder=embedder, repository=repository)

        with self.assertRaisesRegex(EmbeddingProviderError, "1024 finite values"):
            retriever.retrieve("I cannot sign in.")

        self.assertIsNone(repository.search_arguments)


if __name__ == "__main__":
    unittest.main()
