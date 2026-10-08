import math
from dataclasses import dataclass

from app.embedder import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingProviderError,
    VECTOR_DIMENSION,
)
from app.retrieval_repository import RetrievalRepository, RetrievedChunk
from app.schemas import Citation
from app.query_rules import is_billing_dispute_question


@dataclass(frozen=True)
class RetrievalResult:
    citations: list[Citation]
    confidence: float


class StubRetriever:
    """Week 1 placeholder retriever with deterministic outputs."""

    def retrieve(self, question: str, top_k: int = 3) -> RetrievalResult:
        if is_billing_dispute_question(question):
            return RetrievalResult(
                citations=[
                    Citation(
                        source_id="billing-policy-01",
                        title="Billing and Refund Policy",
                        excerpt="Duplicate charges are reviewed within 2 business days and reversed if confirmed.",
                    ),
                    Citation(
                        source_id="support-sla-02",
                        title="Support SLA",
                        excerpt="Billing disputes require human review for final resolution.",
                    ),
                ][:top_k],
                confidence=0.82,
            )

        return RetrievalResult(
            citations=[
                Citation(
                    source_id="general-help-01",
                    title="General Support Playbook",
                    excerpt="Ask clarifying questions and provide concrete next steps with expected timelines.",
                )
            ][:top_k],
            confidence=0.61,
        )


@dataclass(frozen=True)
class VectorRetrievalResult:
    hits: tuple[RetrievedChunk, ...]


class PgVectorRetriever:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        repository: RetrievalRepository,
    ) -> None:
        self._embedder = embedder
        self._repository = repository

    def retrieve(self, question: str, top_k: int = 3) -> VectorRetrievalResult:
        batch = self._embedder.embed([question])
        if len(batch.vectors) != 1:
            raise EmbeddingProviderError(
                f"Embedding provider returned {len(batch.vectors)} vectors for one query."
            )

        query_vector = batch.vectors[0]
        if (
            batch.dimension != VECTOR_DIMENSION
            or len(query_vector) != VECTOR_DIMENSION
            or any(not math.isfinite(value) for value in query_vector)
        ):
            raise EmbeddingProviderError(
                f"Query embedding must contain {VECTOR_DIMENSION} finite values."
            )

        model_info = EmbeddingModelInfo(
            model_name=batch.model_name,
            model_digest=batch.model_digest,
            dimension=batch.dimension,
        )
        hits = self._repository.search(
            query_vector=query_vector,
            embedding_model_info=model_info,
            top_k=top_k,
        )
        return VectorRetrievalResult(hits=hits)
