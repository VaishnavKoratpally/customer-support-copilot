import hashlib
import json
import logging
import math
import time
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evidence_assessment import EvidenceAssessmentDecision, EvidenceAssessmentProposal, EvidenceSufficiencyStatus
from app.evidence_assessor import EvidenceAssessorError, OllamaEvidenceAssessor
from app.llm_provider import OllamaGenerationMetrics, OllamaGenerationResult, OllamaLLMProvider, OllamaProviderError
from app.logging_utils import log_event
from app.prompts import build_evidence_assessor_system_prompt
from app.retrieval_repository import RetrievedChunk
from app.schemas import Citation

logger = logging.getLogger("support_copilot.reviewer_assistance")

FeedbackReason = Literal[
    "incorrect_status",
    "request_omission",
    "unsupported_claim",
    "missing_condition",
    "irrelevant_fact",
    "clarification_problem",
    "assessment_failed",
]


class ReviewerAssistanceNotFoundError(LookupError):
    pass


class ReviewerAssistanceConflictError(RuntimeError):
    pass


class SavedEvidenceError(ValueError):
    pass


class ReviewerAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    trace_id: str = Field(min_length=1)
    request_id: UUID
    reviewer_id: str = Field(min_length=1, max_length=100)


class AssessmentFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["invalid_saved_evidence", "assessor_failed"]
    message: str = Field(min_length=1)


class RecordedReviewerAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: UUID
    trace_id: str
    reviewer_id: str
    state: Literal["running", "completed", "failed"]
    question: str
    citations: list[Citation]
    assessor_model: str
    system_prompt_sha256: str
    schema_sha256: str
    proposed_assessment: EvidenceAssessmentDecision | None
    error: AssessmentFailure | None
    generation_metrics: OllamaGenerationMetrics | None
    elapsed_seconds: float | None = Field(ge=0)
    started_at: datetime
    completed_at: datetime | None

    @model_validator(mode="after")
    def validate_outcome(self) -> "RecordedReviewerAssessment":
        if self.state == "running":
            if any(value is not None for value in (
                self.proposed_assessment, self.error, self.generation_metrics,
                self.elapsed_seconds, self.completed_at,
            )):
                raise ValueError("A running assessment must not have a terminal outcome.")
        else:
            if self.completed_at is None or self.elapsed_seconds is None:
                raise ValueError("A terminal assessment requires completion and elapsed times.")
            if self.state == "completed":
                if self.proposed_assessment is None or self.error is not None:
                    raise ValueError("A completed assessment requires a proposal and no error.")
            elif self.proposed_assessment is not None or self.error is None:
                raise ValueError("A failed assessment requires an error and no proposal.")
        return self


class AssessmentFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=100)
    verdict: Literal["helpful", "needs_correction", "unusable"]
    reasons: list[FeedbackReason] = Field(default_factory=list, max_length=7)
    corrected_status: EvidenceSufficiencyStatus | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_feedback(self) -> "AssessmentFeedbackRequest":
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Feedback reasons must be unique.")
        if self.verdict == "helpful":
            if self.reasons or self.corrected_status is not None:
                raise ValueError("Helpful feedback must not include corrections.")
        elif not self.reasons or self.notes is None:
            raise ValueError("Corrective or unusable feedback requires reasons and notes.")
        if self.corrected_status is not None and "incorrect_status" not in self.reasons:
            raise ValueError("A status correction requires the incorrect_status reason.")
        if "assessment_failed" in self.reasons and (
            self.verdict != "unusable" or self.corrected_status is not None
        ):
            raise ValueError("Failed-assessment feedback must be unusable without a status correction.")
        return self


class RecordedAssessmentFeedback(AssessmentFeedbackRequest):
    feedback_id: UUID
    assessment_id: UUID
    created_at: datetime


class ReviewerAssessmentResponse(BaseModel):
    assessment: RecordedReviewerAssessment
    feedback: list[RecordedAssessmentFeedback]
    advisory_only: Literal[True] = True
    notice: Literal[
        "Unverified model proposal for human review. This does not approve or deliver a response."
    ] = "Unverified model proposal for human review. This does not approve or deliver a response."


class ReviewerAssistanceRepository(Protocol):
    def begin_assessment(
        self,
        *,
        request: ReviewerAssessmentRequest,
        model_name: str,
        system_prompt_sha256: str,
        schema_sha256: str,
    ) -> tuple[RecordedReviewerAssessment, bool]:
        ...

    def finish_assessment(
        self,
        *,
        assessment_id: UUID,
        proposal: EvidenceAssessmentDecision | None,
        error: AssessmentFailure | None,
        generation_metrics: OllamaGenerationMetrics | None,
        elapsed_seconds: float,
    ) -> RecordedReviewerAssessment:
        ...

    def get_assessment(self, *, assessment_id: UUID) -> RecordedReviewerAssessment:
        ...

    def get_feedback(self, *, assessment_id: UUID) -> list[RecordedAssessmentFeedback]:
        ...

    def save_feedback(
        self,
        *,
        assessment_id: UUID,
        feedback: AssessmentFeedbackRequest,
    ) -> RecordedAssessmentFeedback:
        ...


def chunks_from_saved_citations(citations: list[Citation]) -> tuple[RetrievedChunk, ...]:
    chunks: list[RetrievedChunk] = []
    for citation in citations:
        if (
            citation.chunk_id is None or citation.policy_version is None
            or citation.effective_date is None or citation.access_scope is None
            or citation.chunk_index is None or citation.section_path is None
            or citation.cosine_distance is None
        ):
            raise SavedEvidenceError("Saved evidence lacks vector-retrieval provenance; create a new preview.")
        if (
            not citation.source_id.strip() or not citation.title.strip()
            or not citation.excerpt.strip() or not citation.policy_version.strip()
            or not citation.section_path.strip() or citation.chunk_index < 0
            or not math.isfinite(citation.cosine_distance)
        ):
            raise SavedEvidenceError("Saved evidence contains invalid text or retrieval metadata.")
        chunks.append(RetrievedChunk(
            chunk_id=citation.chunk_id,
            source_id=citation.source_id,
            title=citation.title,
            policy_version=citation.policy_version,
            effective_date=citation.effective_date,
            access_scope=citation.access_scope,
            chunk_index=citation.chunk_index,
            section_path=citation.section_path,
            text=citation.excerpt,
            cosine_distance=citation.cosine_distance,
        ))
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise SavedEvidenceError("Saved evidence contains duplicate chunk IDs.")
    return tuple(chunks)


class _MetricsGenerator:
    def __init__(self, provider: OllamaLLMProvider) -> None:
        self.provider = provider
        self.called = False
        self.result: OllamaGenerationResult | None = None

    def generate_structured(
        self, *, model_name: str, system_prompt: str, user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        if self.called:
            raise OllamaProviderError("An assessment attempt permits only one generation call.")
        self.called = True
        self.result = self.provider.generate_structured_with_metrics(
            model_name=model_name, system_prompt=system_prompt,
            user_prompt=user_prompt, response_schema=response_schema,
        )
        return self.result.text


class ReviewerAssistanceService:
    def __init__(
        self, *, repository: ReviewerAssistanceRepository,
        provider: OllamaLLMProvider, model_name: str,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be blank.")
        self.repository = repository
        self.provider = provider
        self.model_name = model_name

    def _response(self, record: RecordedReviewerAssessment) -> ReviewerAssessmentResponse:
        return ReviewerAssessmentResponse(
            assessment=record,
            feedback=self.repository.get_feedback(assessment_id=record.assessment_id),
        )

    def create(self, request: ReviewerAssessmentRequest) -> ReviewerAssessmentResponse:
        record, created = self.repository.begin_assessment(
            request=request,
            model_name=self.model_name,
            system_prompt_sha256=hashlib.sha256(
                build_evidence_assessor_system_prompt().encode("utf-8")
            ).hexdigest(),
            schema_sha256=hashlib.sha256(json.dumps(
                EvidenceAssessmentProposal.model_json_schema(), sort_keys=True,
            ).encode("utf-8")).hexdigest(),
        )
        if not created:
            return self._response(record)

        generator = _MetricsGenerator(self.provider)
        assessor = OllamaEvidenceAssessor(generator=generator, model_name=record.assessor_model)
        started = time.perf_counter()
        proposal = None
        error = None
        try:
            if not record.question.strip():
                raise SavedEvidenceError("The saved question is blank.")
            proposal = assessor.assess(
                question=record.question,
                retrieved_chunks=chunks_from_saved_citations(record.citations),
            )
        except SavedEvidenceError as exc:
            error = AssessmentFailure(code="invalid_saved_evidence", message=str(exc))
        except EvidenceAssessorError as exc:
            error = AssessmentFailure(code="assessor_failed", message=str(exc))

        record = self.repository.finish_assessment(
            assessment_id=record.assessment_id,
            proposal=proposal,
            error=error,
            generation_metrics=generator.result.metrics if generator.result is not None else None,
            elapsed_seconds=time.perf_counter() - started,
        )
        log_event(
            logger, "reviewer_assessment_finished",
            assessment_id=str(record.assessment_id), trace_id=record.trace_id,
            state=record.state, assessor_model=record.assessor_model,
            elapsed_seconds=record.elapsed_seconds,
            error_code=record.error.code if record.error is not None else None,
        )
        return self._response(record)

    def get(self, assessment_id: UUID) -> ReviewerAssessmentResponse:
        return self._response(self.repository.get_assessment(assessment_id=assessment_id))

    def record_feedback(
        self, assessment_id: UUID, feedback: AssessmentFeedbackRequest,
    ) -> RecordedAssessmentFeedback:
        return self.repository.save_feedback(assessment_id=assessment_id, feedback=feedback)
