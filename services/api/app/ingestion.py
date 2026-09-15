from app.chunker import SimpleSectionChunker
from app.embedder import StubEmbeddingProvider
from app.schemas import IngestionChunkPreview, IngestionPreviewRequest, IngestionPreviewResponse


class IngestionPreviewPipeline:
    def __init__(self) -> None:
        self._chunker = SimpleSectionChunker()
        self._embedder = StubEmbeddingProvider()

    def preview(self, payload: IngestionPreviewRequest) -> IngestionPreviewResponse:
        drafts = self._chunker.chunk(
            content=payload.content,
            target_chunk_tokens=payload.target_chunk_tokens,
            overlap_tokens=payload.overlap_tokens,
        )

        chunks: list[IngestionChunkPreview] = []
        total_estimated_tokens = 0

        for idx, draft in enumerate(drafts, start=1):
            embedding_preview = self._embedder.preview(draft.text)
            total_estimated_tokens += draft.token_estimate

            chunks.append(
                IngestionChunkPreview(
                    chunk_index=idx,
                    section_path=draft.section_path,
                    token_estimate=draft.token_estimate,
                    embedding_dimension=embedding_preview.embedding_dimension,
                    checksum_sha256=embedding_preview.checksum_sha256,
                    text=draft.text,
                )
            )

        return IngestionPreviewResponse(
            source_key=payload.metadata.source_key,
            total_chunks=len(chunks),
            total_estimated_tokens=total_estimated_tokens,
            chunks=chunks,
        )