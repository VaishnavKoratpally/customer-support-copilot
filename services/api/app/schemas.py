from typing import Literal

from pydantic import BaseModel, Field


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

