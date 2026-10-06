import unittest
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from app.embedder import EmbeddingBatch, EmbeddingModelInfo, EmbeddingProviderError, VECTOR_DIMENSION
from app.ingestion import (
    IngestionIndexPipeline,
    IngestionPreviewPipeline,
)
from app.ingestion_repository import (
    IndexedChunk,
    IngestionStoreResult,
    IngestionVersionConflict,
    StoredSourceVersion,
    assert_source_version_unchanged,
)
from app.schemas import IngestionIndexRequest, IngestionPreviewRequest, SourceDocumentMetadata

CONTENT = """# Account recovery
Customers can start a password reset from the sign-in page. The reset link is sent to the email
address already associated with the account. Support must never ask for a password or reset link.

# Security review
Suspected unauthorized access requires human security review before access is restored.
"""


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = VECTOR_DIMENSION) -> None:
        self.info = EmbeddingModelInfo(
            model_name="qwen3-embedding:0.6b",
            model_digest="sha256:fake-digest",
            dimension=dimension,
        )
        self.embed_calls = 0

    def model_info(self) -> EmbeddingModelInfo:
        return self.info

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        self.embed_calls += 1
        vectors = tuple((1.0,) + (0.0,) * (self.info.dimension - 1) for _ in texts)
        return EmbeddingBatch(
            model_name=self.info.model_name,
            model_digest=self.info.model_digest,
            dimension=self.info.dimension,
            vectors=vectors,
        )


class InMemoryIngestionRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StoredSourceVersion] = {}
        self.persist_calls = 0

    def get_source_version(
        self,
        *,
        source_key: str,
        policy_version: str,
    ) -> StoredSourceVersion | None:
        return self.records.get((source_key, policy_version))

    def persist_indexed_version(
        self,
        *,
        metadata: SourceDocumentMetadata,
        raw_content: str,
        checksum_sha256: str,
        embedding_model_info: EmbeddingModelInfo,
        chunker_version: str,
        chunk_target_tokens: int,
        chunk_overlap_tokens: int,
        chunks: tuple[IndexedChunk, ...],
    ) -> IngestionStoreResult:
        _ = raw_content
        self.persist_calls += 1
        key = (metadata.source_key, metadata.policy_version)
        existing = self.records.get(key)
        document_id = uuid5(
            NAMESPACE_URL,
            f"customer-support-copilot:{metadata.source_key}\0{metadata.policy_version}",
        )
        if existing is not None:
            assert_source_version_unchanged(
                existing,
                metadata=metadata,
                checksum_sha256=checksum_sha256,
            )
            document_id = existing.document_id
            status = "reindexed"
        else:
            status = "created"

        self.records[key] = StoredSourceVersion(
            document_id=document_id,
            source_key=metadata.source_key,
            title=metadata.title,
            doc_type=metadata.doc_type,
            product_area=metadata.product_area,
            policy_version=metadata.policy_version,
            effective_date=metadata.effective_date,
            access_scope=metadata.access_scope,
            checksum_sha256=checksum_sha256,
            embedding_model=embedding_model_info.model_name,
            embedding_model_digest=embedding_model_info.model_digest,
            embedding_dimension=embedding_model_info.dimension,
            chunker_version=chunker_version,
            chunk_target_tokens=chunk_target_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
            chunk_count=len(chunks),
        )
        return IngestionStoreResult(
            document_id=document_id,
            status=status,
            chunk_count=len(chunks),
        )


class IngestionIndexPipelineTests(unittest.TestCase):
    def setUp(self):
        self.embedder = FakeEmbeddingProvider()
        self.repository = InMemoryIngestionRepository()
        self.pipeline = IngestionIndexPipeline(
            embedder=self.embedder,
            repository=self.repository,
        )

    def payload(
        self,
        *,
        policy_version: str = "v1",
        content: str = CONTENT,
    ) -> IngestionIndexRequest:
        return IngestionIndexRequest(
            metadata=SourceDocumentMetadata(
                source_key="account-recovery",
                title="Account recovery policy",
                doc_type="support_policy",
                product_area="account_access",
                policy_version=policy_version,
                effective_date=date(2026, 10, 6),
                access_scope="internal",
            ),
            content=content,
            target_chunk_tokens=100,
            overlap_tokens=0,
        )

    def test_indexing_records_model_metadata_and_vectors(self):
        result = self.pipeline.index(self.payload())

        self.assertEqual(result.status, "created")
        self.assertEqual(result.embedding_model, "qwen3-embedding:0.6b")
        self.assertEqual(result.embedding_dimension, VECTOR_DIMENSION)
        self.assertGreater(result.total_chunks, 0)
        self.assertEqual(self.embedder.embed_calls, 1)
        self.assertEqual(self.repository.persist_calls, 1)

    def test_identical_reingestion_is_noop_without_embedding(self):
        first = self.pipeline.index(self.payload())
        second = self.pipeline.index(self.payload())

        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(self.embedder.embed_calls, 1)
        self.assertEqual(self.repository.persist_calls, 1)
        self.assertEqual(len(self.repository.records), 1)

    def test_changed_content_requires_a_new_policy_version(self):
        self.pipeline.index(self.payload())
        changed_content = CONTENT + "\nSupport must verify the account holder's identity."

        with self.assertRaisesRegex(IngestionVersionConflict, "new policy_version"):
            self.pipeline.index(self.payload(content=changed_content))

        updated = self.pipeline.index(
            self.payload(policy_version="v2", content=changed_content)
        )
        self.assertEqual(updated.status, "created")
        self.assertEqual(len(self.repository.records), 2)
        self.assertEqual(self.embedder.embed_calls, 2)

    def test_embedding_model_change_reindexes_same_source_version(self):
        first = self.pipeline.index(self.payload())
        self.embedder.info = EmbeddingModelInfo(
            model_name="qwen3-embedding:0.6b",
            model_digest="sha256:updated-digest",
            dimension=VECTOR_DIMENSION,
        )

        second = self.pipeline.index(self.payload())

        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(second.status, "reindexed")
        self.assertEqual(self.embedder.embed_calls, 2)
        stored = self.repository.records[("account-recovery", "v1")]
        self.assertEqual(stored.embedding_model_digest, "sha256:updated-digest")

    def test_dimension_mismatch_is_rejected_before_embedding_or_persistence(self):
        self.embedder.info = EmbeddingModelInfo(
            model_name="qwen3-embedding:0.6b",
            model_digest="sha256:wrong-dimension",
            dimension=768,
        )

        with self.assertRaisesRegex(EmbeddingProviderError, "768 dimensions"):
            self.pipeline.index(self.payload())

        self.assertEqual(self.embedder.embed_calls, 0)
        self.assertEqual(self.repository.persist_calls, 0)

    def test_preview_does_not_report_a_placeholder_embedding_dimension(self):
        payload = self.payload()
        preview = IngestionPreviewPipeline().preview(
            IngestionPreviewRequest(**payload.model_dump())
        )

        self.assertNotIn("embedding_dimension", preview.model_dump()["chunks"][0])
        self.assertEqual(len(preview.chunks[0].checksum_sha256), 64)


if __name__ == "__main__":
    unittest.main()
