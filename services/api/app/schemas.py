from typing import Literal
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.review_taxonomy import RejectionReasonCode

ReviewStatus = Literal["approve", "edit", "reject"]
DraftReviewStatus = Literal["not_required", "pending_review"]
FinalReviewStatus = Literal["approved", "edited", "rejected"]
ReviewLifecycleStatus = Literal[
    "not_required", "pending_review", "approved", "edited", "rejected"
]
DeliverableReviewStatus = Literal["not_required", "approved", "edited"]
DraftMode = Literal["generated", "preview_only"]


class DraftModelCallMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_duration_ns: int | None = Field(default=None, ge=0)
    load_duration_ns: int | None = Field(default=None, ge=0)
    prompt_eval_count: int | None = Field(default=None, ge=0)
    prompt_eval_duration_ns: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)
    eval_duration_ns: int | None = Field(default=None, ge=0)
    done_reason: str | None = None
    done: bool | None = None


class SupportDraftGenerationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal[
        "generated",
        "no_retrieved_evidence",
        "clarification_needed",
        "insufficient_evidence",
        "no_relevant_evidence",
        "conflicting_evidence",
    ]
    retrieved_chunk_count: int = Field(ge=0)
    retrieval_top_k: int = Field(ge=1, le=10)
    assessor_model: str | None = None
    assessor_system_prompt_sha256: str | None = None
    assessor_user_prompt_sha256: str | None = None
    assessor_schema_sha256: str | None = None
    assessor_elapsed_seconds: float | None = Field(default=None, ge=0)
    assessor_metrics: DraftModelCallMetrics | None = None
    generator_model: str | None = None
    generator_system_prompt_sha256: str | None = None
    generator_user_prompt_sha256: str | None = None
    generator_schema_sha256: str | None = None
    generator_elapsed_seconds: float | None = Field(default=None, ge=0)
    generator_metrics: DraftModelCallMetrics | None = None
    generator_max_output_tokens: int | None = Field(default=None, ge=1)
    generation_completion_verified: bool | None = None
    total_elapsed_seconds: float = Field(ge=0)


class Citation(BaseModel):
    source_id: str
    title: str
    excerpt: str
    chunk_id: UUID | None = None
    policy_version: str | None = None
    effective_date: date | None = None
    access_scope: Literal["public", "internal"] | None = None
    chunk_index: int | None = None
    section_path: str | None = None
    cosine_distance: float | None = Field(
        default=None,
        description="Raw cosine distance; lower values are closer, not a confidence score.",
    )


class SupportDraftRequest(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    ticket_id: str | None = None
    customer_tier: Literal["free", "pro", "enterprise"] | None = None


class SupportDraftResponse(BaseModel):
    trace_id: str
    intent: str
    risk_level: Literal["low", "medium", "high"]
    model_used: str
    draft: str
    citations: list[Citation]
    retrieval_confidence: float | None
    answer_confidence: float | None
    requires_human_review: bool
    review_status: DraftReviewStatus
    escalation_reason: str | None = None
    citation_source_ids: list[str]
    citation_contract_passed: bool
    review_triggers: list[str]
    draft_mode: DraftMode = "generated"
    evidence_assessment: dict[str, object] | None = None
    generation_metadata: SupportDraftGenerationMetadata | None = None

class RetrievalQueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    top_k: int = Field(default=3, ge=1, le=10)


class RetrievalHit(BaseModel):
    rank: int
    chunk_id: UUID
    source_id: str
    title: str
    policy_version: str
    effective_date: date
    access_scope: Literal["public", "internal"]
    chunk_index: int
    section_path: str
    excerpt: str
    cosine_distance: float = Field(
        description="Raw cosine distance; lower values are closer, not a confidence score."
    )


class RetrievalQueryResponse(BaseModel):
    query: str
    top_k: int
    hits: list[RetrievalHit]

class SourceDocumentMetadata(BaseModel):
    source_key: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=3, max_length=300)
    doc_type: str = Field(min_length=2, max_length=100)
    product_area: str = Field(min_length=2, max_length=100)
    policy_version: str = Field(min_length=1, max_length=50)
    effective_date: date
    access_scope: Literal["public", "internal", "restricted"]


class IngestionDocumentRequest(BaseModel):
    metadata: SourceDocumentMetadata
    content: str = Field(min_length=50, max_length=100000)
    target_chunk_tokens: int = Field(default=450, ge=100, le=1200)
    overlap_tokens: int = Field(default=75, ge=0, le=300)


class IngestionPreviewRequest(IngestionDocumentRequest):
    pass


class IngestionIndexRequest(IngestionDocumentRequest):
    pass


class IngestionChunkPreview(BaseModel):
    chunk_index: int
    section_path: str
    token_estimate: int
    checksum_sha256: str
    text: str


class IngestionPreviewResponse(BaseModel):
    source_key: str
    total_chunks: int
    total_estimated_tokens: int
    chunks: list[IngestionChunkPreview]


class IngestionIndexResponse(BaseModel):
    document_id: UUID
    source_key: str
    policy_version: str
    status: Literal["created", "reindexed", "unchanged"]
    total_chunks: int
    checksum_sha256: str
    embedding_model: str
    embedding_model_digest: str
    embedding_dimension: int


class SupportReviewRequest(BaseModel):
    trace_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1, max_length=100)
    status: ReviewStatus
    edited_draft: str | None = Field(default=None, max_length=5000)
    rejection_reason_code: RejectionReasonCode | None = Field(default=None, max_length=100)

class ReviewAuditEventPayload(BaseModel):
    event_type: Literal["support_review_decision_recorded"]
    actor_type: Literal["agent"]
    actor_id: str
    trace_id: str
    status: ReviewStatus
    rejection_reason_code: RejectionReasonCode | None = None
    requires_follow_up: bool
    reviewed_at: datetime
    ai_draft_sha256: str
    final_draft_sha256: str | None = None

class SupportReviewResponse(BaseModel):
    trace_id: str
    reviewer_id: str
    status: ReviewStatus
    review_status: FinalReviewStatus
    final_draft: str
    requires_follow_up: bool
    reviewed_at: datetime
    audit_event_payload: ReviewAuditEventPayload


class SupportDeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)


class SupportDeliveryResponse(BaseModel):
    delivery_id: UUID
    trace_id: str
    delivery_status: Literal["simulated"]
    review_status: DeliverableReviewStatus
    content_sha256: str
    simulated_at: datetime
