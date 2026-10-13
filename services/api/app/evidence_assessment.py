from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.retrieval_repository import RetrievedChunk

EvidenceFinding = Literal[
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


class SupportingFactAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(
        min_length=1,
        description="A concise declarative proposition, not a question.",
    )
    finding: Literal["supported"]
    evidence: list[EvidenceQuote]

    @field_validator("claim")
    @classmethod
    def claim_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Claim must not be blank.")
        if value.rstrip().endswith("?"):
            raise ValueError("Claim must be declarative, not a question.")
        return value


class RequestedInformationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_information: str = Field(
        min_length=1,
        description=(
            "A concise label for the fact or value the customer wants, not the "
            "customer's full question."
        ),
    )
    finding: EvidenceFinding
    answer: str | None = Field(
        description=(
            "A concise declarative answer proposition when evidence determines "
            "the requested information; otherwise null."
        )
    )
    evidence: list[EvidenceQuote]

    @field_validator("requested_information")
    @classmethod
    def requested_information_must_be_a_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Requested information must not be blank.")
        if value.rstrip().endswith("?"):
            raise ValueError(
                "Requested information must describe the requested fact, not repeat the question."
            )
        return value

    @field_validator("answer")
    @classmethod
    def answer_must_be_declarative(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Answer must not be blank.")
        if value.rstrip().endswith("?"):
            raise ValueError("Answer must be declarative, not a question.")
        return value

    @model_validator(mode="after")
    def validate_answer_matches_finding(self) -> "RequestedInformationAssessment":
        answer_is_determined = self.finding in {"supported", "contradicted"}
        if answer_is_determined and self.answer is None:
            raise ValueError(
                "Supported or contradicted requested information requires an answer."
            )
        if not answer_is_determined and self.answer is not None:
            raise ValueError(
                "Undetermined requested information must not include an answer."
            )
        return self


class EvidenceAssessmentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_information: list[RequestedInformationAssessment] = Field(
        description=(
            "Atomic facts or values the customer wants, with an answer only "
            "when retrieved evidence determines one."
        )
    )
    supporting_facts: list[SupportingFactAssessment] = Field(
        description=(
            "Directly relevant, supported propositions that may help answer "
            "the request but were not explicitly asked about."
        )
    )
    clarifying_question: str | None = None

    @field_validator("clarifying_question")
    @classmethod
    def clarifying_question_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Clarifying question must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_assessment_shape(self) -> "EvidenceAssessmentProposal":
        if self.clarifying_question is not None and (
            self.requested_information or self.supporting_facts
        ):
            raise ValueError(
                "A clarification request must not include requested information "
                "or supporting facts."
            )
        if self.clarifying_question is None and not self.requested_information:
            raise ValueError(
                "An assessment must include requested information or a clarifying question."
            )
        normalized_requests = [
            " ".join(item.requested_information.casefold().split())
            for item in self.requested_information
        ]
        if len(normalized_requests) != len(set(normalized_requests)):
            raise ValueError(
                "Requested information items must not duplicate one another."
            )

        determined_answers = [
            " ".join(item.answer.casefold().split())
            for item in self.requested_information
            if item.answer is not None
        ]
        fact_claims = [
            " ".join(item.claim.casefold().split())
            for item in self.supporting_facts
        ]
        answer_and_fact_claims = [*determined_answers, *fact_claims]
        if len(answer_and_fact_claims) != len(set(answer_and_fact_claims)):
            raise ValueError(
                "Requested answers and supporting facts must not duplicate one another."
            )
        return self


class EvidenceAssessmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceSufficiencyStatus
    action: EvidenceAction
    requested_information: list[RequestedInformationAssessment]
    supporting_facts: list[SupportingFactAssessment]
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


def aggregate_evidence_sufficiency_status(
    requested_findings: set[EvidenceFinding],
    *,
    has_supporting_facts: bool,
    clarification_needed: bool = False,
) -> EvidenceSufficiencyStatus:
    if clarification_needed:
        return "clarification_needed"
    if "conflicting" in requested_findings:
        return "conflicting"
    if requested_findings.issubset({"supported", "contradicted"}):
        return "sufficient"
    if requested_findings.intersection({"supported", "contradicted"}) or (
        has_supporting_facts
    ):
        return "partial"
    if "related_but_not_supported" in requested_findings:
        return "insufficient"
    return "none"


def validate_and_aggregate_assessment(
    proposal: EvidenceAssessmentProposal,
    *,
    retrieved_chunks: Sequence[RetrievedChunk],
) -> EvidenceAssessmentDecision:
    if proposal.clarifying_question is not None:
        status = aggregate_evidence_sufficiency_status(
            set(),
            has_supporting_facts=False,
            clarification_needed=True,
        )
        return EvidenceAssessmentDecision(
            status=status,
            action=_ACTION_BY_STATUS[status],
            requested_information=[],
            supporting_facts=[],
            clarifying_question=proposal.clarifying_question,
        )

    chunks_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
    for item in proposal.requested_information:
        _validate_finding_evidence(item.finding, item.evidence, chunks_by_id)
    for fact in proposal.supporting_facts:
        _validate_finding_evidence(fact.finding, fact.evidence, chunks_by_id)

    requested_findings = {item.finding for item in proposal.requested_information}
    status = aggregate_evidence_sufficiency_status(
        requested_findings,
        has_supporting_facts=bool(proposal.supporting_facts),
    )

    return EvidenceAssessmentDecision(
        status=status,
        action=_ACTION_BY_STATUS[status],
        requested_information=proposal.requested_information,
        supporting_facts=proposal.supporting_facts,
    )


def _validate_finding_evidence(
    finding: EvidenceFinding,
    evidence: Sequence[EvidenceQuote],
    chunks_by_id: dict[UUID, RetrievedChunk],
) -> None:
    evidence_chunk_ids = {item.chunk_id for item in evidence}

    if finding in {"supported", "contradicted", "related_but_not_supported"}:
        if not evidence:
            raise EvidenceAssessmentValidationError(
                f"Finding '{finding}' requires at least one evidence quote."
            )
    elif finding == "no_relevant_evidence":
        if evidence:
            raise EvidenceAssessmentValidationError(
                "A finding of no relevant evidence must not cite chunks."
            )
    elif finding == "conflicting":
        if len(evidence_chunk_ids) < 2:
            raise EvidenceAssessmentValidationError(
                "Conflicting evidence must cite at least two distinct retrieved chunks."
            )

    for item in evidence:
        chunk = chunks_by_id.get(item.chunk_id)
        if chunk is None:
            raise EvidenceAssessmentValidationError(
                f"Evidence references chunk '{item.chunk_id}' that was not retrieved."
            )
        if item.quote not in chunk.text:
            raise EvidenceAssessmentValidationError(
                f"Evidence quote is not an exact substring of chunk '{item.chunk_id}'."
            )
