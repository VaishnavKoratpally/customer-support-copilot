from hashlib import sha256
from math import isfinite
from uuid import UUID

from app.chunker import SimpleSectionChunker
from app.embedder import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingProviderError,
    VECTOR_DIMENSION,
)
from app.ingestion_repository import (
    IndexedChunk,
    IngestionRepository,
    IngestionStatus,
    IngestionVersionConflict,
    assert_source_version_unchanged,
    index_configuration_matches,
)
from app.schemas import (
    IngestionChunkPreview,
    IngestionIndexRequest,
    IngestionIndexResponse,
    IngestionPreviewRequest,
    IngestionPreviewResponse,
)


class IngestionPreviewPipeline:
    def __init__(self) -> None:
        self._chunker = SimpleSectionChunker()

    def preview(self, payload: IngestionPreviewRequest) -> IngestionPreviewResponse:
        drafts = self._chunker.chunk(
            content=payload.content,
            target_chunk_tokens=payload.target_chunk_tokens,
            overlap_tokens=payload.overlap_tokens,
        )

        chunks: list[IngestionChunkPreview] = []
        total_estimated_tokens = 0

        for idx, draft in enumerate(drafts, start=1):
            checksum = sha256(draft.text.encode("utf-8")).hexdigest()
            total_estimated_tokens += draft.token_estimate

            chunks.append(
                IngestionChunkPreview(
                    chunk_index=idx,
                    section_path=draft.section_path,
                    token_estimate=draft.token_estimate,
                    checksum_sha256=checksum,
                    text=draft.text,
                )
            )

        return IngestionPreviewResponse(
            source_key=payload.metadata.source_key,
            total_chunks=len(chunks),
            total_estimated_tokens=total_estimated_tokens,
            chunks=chunks,
        )


class IngestionInputError(ValueError):
    pass


class IngestionIndexPipeline:
    chunker_version = "simple-section-v1"

    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        repository: IngestionRepository,
    ) -> None:
        self._chunker = SimpleSectionChunker()
        self._embedder = embedder
        self._repository = repository

    def index(self, payload: IngestionIndexRequest) -> IngestionIndexResponse:
        checksum = sha256(payload.content.encode("utf-8")).hexdigest()
        existing = self._repository.get_source_version(
            source_key=payload.metadata.source_key,
            policy_version=payload.metadata.policy_version,
        )
        if existing is not None:
            assert_source_version_unchanged(
                existing,
                metadata=payload.metadata,
                checksum_sha256=checksum,
            )

        drafts = self._chunker.chunk(
            content=payload.content,
            target_chunk_tokens=payload.target_chunk_tokens,
            overlap_tokens=payload.overlap_tokens,
        )
        if not drafts:
            raise IngestionInputError("Document content produced no indexable chunks.")

        model_info = self._embedder.model_info()
        self._validate_model_info(model_info)
        if existing is not None and index_configuration_matches(
            existing,
            embedding_model_info=model_info,
            chunker_version=self.chunker_version,
            chunk_target_tokens=payload.target_chunk_tokens,
            chunk_overlap_tokens=payload.overlap_tokens,
            chunk_count=len(drafts),
        ):
            return self._response(
                payload=payload,
                document_id=existing.document_id,
                status="unchanged",
                chunk_count=existing.chunk_count,
                checksum_sha256=checksum,
                model_info=model_info,
            )

        batch = self._embedder.embed([draft.text for draft in drafts])
        self._validate_batch(
            batch=batch,
            expected_model_info=model_info,
            chunk_count=len(drafts),
        )
        indexed_chunks = tuple(
            IndexedChunk(
                chunk_index=index,
                section_path=draft.section_path,
                text=draft.text,
                token_estimate=draft.token_estimate,
                checksum_sha256=sha256(draft.text.encode("utf-8")).hexdigest(),
                embedding=vector,
            )
            for index, (draft, vector) in enumerate(
                zip(drafts, batch.vectors, strict=True),
                start=1,
            )
        )
        stored = self._repository.persist_indexed_version(
            metadata=payload.metadata,
            raw_content=payload.content,
            checksum_sha256=checksum,
            embedding_model_info=model_info,
            chunker_version=self.chunker_version,
            chunk_target_tokens=payload.target_chunk_tokens,
            chunk_overlap_tokens=payload.overlap_tokens,
            chunks=indexed_chunks,
        )
        return self._response(
            payload=payload,
            document_id=stored.document_id,
            status=stored.status,
            chunk_count=stored.chunk_count,
            checksum_sha256=checksum,
            model_info=model_info,
        )

    @staticmethod
    def _validate_model_info(model_info: EmbeddingModelInfo) -> None:
        if model_info.dimension != VECTOR_DIMENSION:
            raise EmbeddingProviderError(
                f"Embedding model reports {model_info.dimension} dimensions; "
                f"pgvector is configured for {VECTOR_DIMENSION}."
            )
        if model_info.model_name.strip() == "" or model_info.model_digest.strip() == "":
            raise EmbeddingProviderError("Embedding model name and digest must be present.")

    @staticmethod
    def _validate_batch(
        *,
        batch: EmbeddingBatch,
        expected_model_info: EmbeddingModelInfo,
        chunk_count: int,
    ) -> None:
        if (
            batch.model_name != expected_model_info.model_name
            or batch.model_digest != expected_model_info.model_digest
            or batch.dimension != expected_model_info.dimension
        ):
            raise EmbeddingProviderError(
                "Embedding model metadata changed while indexing; retry the request."
            )
        if len(batch.vectors) != chunk_count:
            raise EmbeddingProviderError(
                f"Embedding provider returned {len(batch.vectors)} vectors "
                f"for {chunk_count} chunks."
            )
        for index, vector in enumerate(batch.vectors, start=1):
            if len(vector) != VECTOR_DIMENSION:
                raise EmbeddingProviderError(
                    f"Embedding vector {index} has {len(vector)} dimensions; "
                    f"expected {VECTOR_DIMENSION}."
                )
            if any(not isfinite(value) for value in vector):
                raise EmbeddingProviderError(
                    f"Embedding vector {index} contains a non-finite value."
                )

    @staticmethod
    def _response(
        *,
        payload: IngestionIndexRequest,
        document_id: UUID,
        status: IngestionStatus,
        chunk_count: int,
        checksum_sha256: str,
        model_info: EmbeddingModelInfo,
    ) -> IngestionIndexResponse:
        return IngestionIndexResponse(
            document_id=document_id,
            source_key=payload.metadata.source_key,
            policy_version=payload.metadata.policy_version,
            status=status,
            total_chunks=chunk_count,
            checksum_sha256=checksum_sha256,
            embedding_model=model_info.model_name,
            embedding_model_digest=model_info.model_digest,
            embedding_dimension=model_info.dimension,
        )