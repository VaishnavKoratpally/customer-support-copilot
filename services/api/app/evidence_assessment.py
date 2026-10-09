from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.retrieval_repository import RetrievedChunk

ClaimFinding = Literal[
    "supported",
    "contradicted",
    "related_but_not_supported",
    "no_relevant_evidence",
    "conflicting",
]

EvidenceSufficiencyStatus = Literal[
    "sufficient",
    "partial",
    "insufficient",
    "none",
    "clarification_needed",
    "conflicting",
]

EvidenceAction = Literal[
    "draft_from_determined_claims",
    "draft_determined_claims_and_escalate",
    "state_missing_fact_and_escalate",
    "abstain_and_escalate",
    "ask_clarifying_question",
    "abstain_and_escalate_conflict",
]


class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    quote: str = Field(min_length=1)

    @field_validator("quote")
    @classmethod
    def quote_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence quote must not be blank.")
        return value


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    finding: ClaimFinding
    evidence: list[EvidenceQuote]

    @field_validator("claim")
    @classmethod
    def claim_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Claim must not be blank.")
        return value


class EvidenceAssessmentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimAssessment]
    clarifying_question: str | None = None

    @field_validator("clarifying_question")
    @classmethod
    def clarifying_question_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Clarifying question must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_assessment_shape(self) -> "EvidenceAssessmentProposal":
        if self.clarifying_question is not None and self.claims:
            raise ValueError(
                "A clarification request must not include claim assessments."
            )
        if self.clarifying_question is None and not self.claims:
            raise ValueError(
                "An assessment must include claims or a clarifying question."
            )
        return self


class EvidenceAssessmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceSufficiencyStatus
    action: EvidenceAction
    claims: list[ClaimAssessment]
    clarifying_question: str | None = None


class EvidenceAssessmentValidationError(ValueError):
    pass


_ACTION_BY_STATUS: dict[EvidenceSufficiencyStatus, EvidenceAction] = {
    "sufficient": "draft_from_determined_claims",
    "partial": "draft_determined_claims_and_escalate",
    "insufficient": "state_missing_fact_and_escalate",
    "none": "abstain_and_escalate",
    "clarification_needed": "ask_clarifying_question",
    "conflicting": "abstain_and_escalate_conflict",
}


def validate_and_aggregate_assessment(
    proposal: EvidenceAssessmentProposal,
    *,
    retrieved_chunks: Sequence[RetrievedChunk],
) -> EvidenceAssessmentDecision:
    if proposal.clarifying_question is not None:
        return EvidenceAssessmentDecision(
            status="clarification_needed",
            action=_ACTION_BY_STATUS["clarification_needed"],
            claims=[],
            clarifying_question=proposal.clarifying_question,
        )

    chunks_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
    for claim in proposal.claims:
        _validate_claim_evidence(claim, chunks_by_id)

    findings = {claim.finding for claim in proposal.claims}
    if "conflicting" in findings:
        status: EvidenceSufficiencyStatus = "conflicting"
    elif findings.issubset({"supported", "contradicted"}):
        status = "sufficient"
    elif findings.intersection({"supported", "contradicted"}):
        status = "partial"
    elif "related_but_not_supported" in findings:
        status = "insufficient"
    else:
        status = "none"

    return EvidenceAssessmentDecision(
        status=status,
        action=_ACTION_BY_STATUS[status],
        claims=proposal.claims,
    )


def _validate_claim_evidence(
    claim: ClaimAssessment,
    chunks_by_id: dict[UUID, RetrievedChunk],
) -> None:
    evidence_chunk_ids = {item.chunk_id for item in claim.evidence}

    if claim.finding in {"supported", "contradicted", "related_but_not_supported"}:
        if not claim.evidence:
            raise EvidenceAssessmentValidationError(
                f"Finding '{claim.finding}' requires at least one evidence quote."
            )
    elif claim.finding == "no_relevant_evidence":
        if claim.evidence:
            raise EvidenceAssessmentValidationError(
                "A claim marked as having no relevant evidence must not cite chunks."
            )
    elif claim.finding == "conflicting":
        if len(evidence_chunk_ids) < 2:
            raise EvidenceAssessmentValidationError(
                "Conflicting evidence must cite at least two distinct retrieved chunks."
            )

    for item in claim.evidence:
        chunk = chunks_by_id.get(item.chunk_id)
        if chunk is None:
            raise EvidenceAssessmentValidationError(
                f"Evidence references chunk '{item.chunk_id}' that was not retrieved."
            )
        if item.quote not in chunk.text:
            raise EvidenceAssessmentValidationError(
                f"Evidence quote is not an exact substring of chunk '{item.chunk_id}'."
            )
