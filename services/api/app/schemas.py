from typing import Literal
from datetime import date, datetime
from pydantic import BaseModel, Field
from app.review_taxonomy import RejectionReasonCode

ReviewStatus = Literal["approve", "edit", "reject"]

class Citation(BaseModel):
    source_id: str
    title: str
    excerpt: str


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
    retrieval_confidence: float
    answer_confidence: float
    requires_human_review: bool
    escalation_reason: str | None = None
    citation_source_ids: list[str]
    citation_contract_passed: bool
    review_triggers: list[str]

class RetrievalQueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    top_k: int = Field(default=3, ge=1, le=10)


class RetrievalHit(BaseModel):
    rank: int
    source_id: str
    title: str
    excerpt: str


class RetrievalQueryResponse(BaseModel):
    query: str
    top_k: int
    retrieval_confidence: float
    hits: list[RetrievalHit]

class SourceDocumentMetadata(BaseModel):
    source_key: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=3, max_length=300)
    doc_type: str = Field(min_length=2, max_length=100)
    product_area: str = Field(min_length=2, max_length=100)
    policy_version: str = Field(min_length=1, max_length=50)
    effective_date: date
    access_scope: Literal["public", "internal", "restricted"]


class IngestionPreviewRequest(BaseModel):
    metadata: SourceDocumentMetadata
    content: str = Field(min_length=50, max_length=100000)
    target_chunk_tokens: int = Field(default=450, ge=100, le=1200)
    overlap_tokens: int = Field(default=75, ge=0, le=300)


class IngestionChunkPreview(BaseModel):
    chunk_index: int
    section_path: str
    token_estimate: int
    embedding_dimension: int
    checksum_sha256: str
    text: str


class IngestionPreviewResponse(BaseModel):
    source_key: str
    total_chunks: int
    total_estimated_tokens: int
    chunks: list[IngestionChunkPreview]

class SupportReviewRequest(BaseModel):
    trace_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1, max_length=100)
    status: ReviewStatus
    ai_draft: str = Field(min_length=1, max_length=5000)
    edited_draft: str | None = Field(default=None, max_length=5000)
    rejection_reason_code: RejectionReasonCode | None = Field(default=None, max_length=100)


class SupportReviewResponse(BaseModel):
    trace_id: str
    reviewer_id: str
    status: ReviewStatus
    final_draft: str
    requires_follow_up: bool
    reviewed_at: datetime
    audit_event_payload: ReviewAuditEventPayload

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