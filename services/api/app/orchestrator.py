import hashlib
import json
import logging
import time
from dataclasses import asdict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.evidence_assessment import (
    EvidenceAssessmentDecision,
    EvidenceAssessmentProposal,
    EvidenceAssessmentValidationError,
)
from app.evidence_assessor import EvidenceAssessorError, OllamaEvidenceAssessor
from app.logging_utils import log_event
from app.config import Settings
from app.llm_provider import (
    DraftGenerationProvider,
    OllamaGenerationMetrics,
    OllamaGenerationResult,
    OllamaProviderError,
)
from app.prompts import (
    build_customer_reply_system_prompt,
    build_customer_reply_user_prompt,
    build_evidence_assessor_system_prompt,
    build_evidence_assessor_user_prompt,
)
from app.retrieval_repository import RetrievedChunk
from app.retriever import PgVectorRetriever, StubRetriever
from app.routing import RoutingDecision, route_question
from app.schemas import (
    Citation,
    DraftModelCallMetrics,
    DraftReviewStatus,
    SupportDraftGenerationMetadata,
    SupportDraftRequest,
    SupportDraftResponse,
)
from app.prompts import build_support_system_prompt, build_support_user_prompt
from app.confidence import compute_answer_confidence
from app.review_policy import evaluate_review_policy
from app.llm_provider import LLMProvider

logger = logging.getLogger("support_copilot.orchestrator")


class DraftGenerationError(RuntimeError):
    pass


class GeneratedCustomerReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: str = Field(min_length=1, max_length=2000)

    @field_validator("draft")
    @classmethod
    def draft_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Generated customer reply must not be blank.")
        return value


class _MetricsStructuredGenerator:
    def __init__(self, provider: DraftGenerationProvider) -> None:
        self._provider = provider
        self.result: OllamaGenerationResult | None = None

    def generate_structured(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        if self.result is not None:
            raise OllamaProviderError(
                "A support draft request permits one evidence-assessment call."
            )
        self.result = self._provider.generate_structured_with_metrics(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )
        return self.result.text


def _citation_from_chunk(chunk: RetrievedChunk) -> Citation:
    return Citation(
        source_id=chunk.source_id,
        title=chunk.title,
        excerpt=chunk.text,
        chunk_id=chunk.chunk_id,
        policy_version=chunk.policy_version,
        effective_date=chunk.effective_date,
        access_scope=chunk.access_scope,
        chunk_index=chunk.chunk_index,
        section_path=chunk.section_path,
        cosine_distance=chunk.cosine_distance,
    )


def _assessment_citations(
    *,
    decision: EvidenceAssessmentDecision,
    retrieved_chunks: tuple[RetrievedChunk, ...],
) -> list[Citation]:
    used_chunk_ids = {
        quote.chunk_id
        for item in decision.requested_information
        for quote in item.evidence
    }
    used_chunk_ids.update(
        quote.chunk_id
        for fact in decision.supporting_facts
        for quote in fact.evidence
    )
    return [
        _citation_from_chunk(chunk)
        for chunk in retrieved_chunks
        if chunk.chunk_id in used_chunk_ids
    ]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_schema(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _call_metrics(value: OllamaGenerationResult) -> DraftModelCallMetrics:
    return DraftModelCallMetrics(**asdict(value.metrics))


def _validate_generation_completion(
    *,
    metrics: OllamaGenerationMetrics,
    output_limit: int,
    stage: str,
) -> None:
    if metrics.done is False or metrics.done_reason == "length":
        raise DraftGenerationError(
            f"Ollama {stage} output hit its generation limit or did not complete."
        )
    if metrics.done_reason not in (None, "stop"):
        raise DraftGenerationError(
            f"Ollama {stage} output ended with unsupported reason "
            f"{metrics.done_reason!r}."
        )
    if metrics.eval_count is not None and metrics.eval_count >= output_limit:
        raise DraftGenerationError(
            f"Ollama {stage} output reached its {output_limit}-token limit."
        )
    if (
        metrics.done is not True
        and metrics.done_reason != "stop"
        and metrics.eval_count is None
    ):
        raise DraftGenerationError(
            f"Ollama did not return completion metadata for the {stage} output."
        )


def _unique_source_ids(citations: list[Citation]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for citation in citations:
        source_id = citation.source_id
        if source_id not in seen:
            seen.add(source_id)
            ordered.append(source_id)
    return ordered

class StubRetrievalCopilotOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        retriever: StubRetriever,
        llm_provider: LLMProvider,
    ) -> None:
        self._settings = settings
        self._retriever = retriever
        self._llm_provider = llm_provider

    def draft_reply(self, payload: SupportDraftRequest) -> SupportDraftResponse:
        trace_id = str(uuid4())
        route = route_question(payload.question)
        retrieval = self._retriever.retrieve(payload.question)
        citation_source_ids = _unique_source_ids(retrieval.citations)
        citation_contract_passed = len(citation_source_ids) > 0

        model_name = self._settings.main_model
        escalation_reason: str | None = None
        if retrieval.confidence < self._settings.retrieval_confidence_threshold:
            model_name = self._settings.escalation_model
            escalation_reason = "low_retrieval_confidence"
        
        system_prompt = build_support_system_prompt()
        user_prompt = build_support_user_prompt(
            question=payload.question,
            intent=route.intent,
            citations=retrieval.citations,
        )

        draft = self._llm_provider.draft_response(
            question=payload.question,
            intent=route.intent,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        if citation_contract_passed:
            draft = f"{draft}\n\nSources: " + ", ".join(f"[{sid}]" for sid in citation_source_ids)

        answer_confidence = compute_answer_confidence(
            retrieval_confidence=retrieval.confidence,
            risk_level=route.risk_level,
        )

        review_decision = evaluate_review_policy(
            intent=route.intent,
            answer_confidence=answer_confidence,
            answer_confidence_threshold=self._settings.answer_confidence_threshold,
            citation_contract_passed=citation_contract_passed,
        )
        
        requires_human_review = review_decision.requires_human_review
        review_status: DraftReviewStatus = (
            "pending_review" if requires_human_review else "not_required"
        )
        if "missing_citations" in review_decision.triggers:
            escalation_reason = "missing_citations"

        elif "low_answer_confidence" in review_decision.triggers and escalation_reason is None:
            escalation_reason = "policy_gate"

        elif "high_risk_intent" in review_decision.triggers and escalation_reason is None:
            escalation_reason = "policy_gate"
        
        log_event(
            logger,
            "support_draft_decision",
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_name,
            retrieval_confidence=retrieval.confidence,
            answer_confidence=answer_confidence,
            requires_human_review=requires_human_review,
            review_status=review_status,
            escalation_reason=escalation_reason,
            review_triggers=review_decision.triggers,
        )

        return SupportDraftResponse(
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_name,
            draft=draft,
            citations=retrieval.citations,
            retrieval_confidence=retrieval.confidence,
            answer_confidence=answer_confidence,
            requires_human_review=requires_human_review,
            review_status=review_status,
            escalation_reason=escalation_reason,
            citation_source_ids=citation_source_ids,
            citation_contract_passed=citation_contract_passed,
            review_triggers=review_decision.triggers,
        )


class PreviewOnlyDraftOrchestrator:
    def __init__(self, *, retriever: PgVectorRetriever) -> None:
        self._retriever = retriever

    def draft_reply(self, payload: SupportDraftRequest) -> SupportDraftResponse:
        trace_id = str(uuid4())
        route = route_question(payload.question)
        retrieval = self._retriever.retrieve(payload.question, top_k=3)
        citations = [
            Citation(
                source_id=hit.source_id,
                title=hit.title,
                excerpt=hit.text,
                chunk_id=hit.chunk_id,
                policy_version=hit.policy_version,
                effective_date=hit.effective_date,
                access_scope=hit.access_scope,
                chunk_index=hit.chunk_index,
                section_path=hit.section_path,
                cosine_distance=hit.cosine_distance,
            )
            for hit in retrieval.hits
        ]
        citation_source_ids = _unique_source_ids(citations)
        citation_contract_passed = bool(citation_source_ids)
        has_evidence = bool(retrieval.hits)
        review_triggers = ["evidence_assessment_not_validated"]
        if not has_evidence:
            review_triggers.append("no_retrieved_evidence")
        if route.risk_level == "high":
            review_triggers.append("high_risk_intent")

        if has_evidence:
            draft = (
                "No customer response was generated. Retrieved evidence has not been "
                "assessed for sufficiency. A support agent must review the sources and "
                "draft a response manually."
            )
            escalation_reason = "evidence_assessment_not_validated"
        else:
            draft = (
                "No customer response was generated because no eligible support evidence "
                "was retrieved. A support agent must review the request and respond manually."
            )
            escalation_reason = "no_retrieved_evidence"

        model_used = "none_preview_only"
        log_event(
            logger,
            "support_draft_preview",
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_used,
            retrieved_chunk_count=len(retrieval.hits),
            citation_source_ids=citation_source_ids,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason=escalation_reason,
            review_triggers=review_triggers,
        )

        return SupportDraftResponse(
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_used,
            draft=draft,
            citations=citations,
            retrieval_confidence=None,
            answer_confidence=None,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason=escalation_reason,
            citation_source_ids=citation_source_ids,
            citation_contract_passed=citation_contract_passed,
            review_triggers=review_triggers,
            draft_mode="preview_only",
        )


class GeneratedDraftOrchestrator:
    retrieval_top_k = 3
    assessor_max_output_tokens = 1024

    def __init__(
        self,
        *,
        retriever: PgVectorRetriever,
        provider: DraftGenerationProvider,
        assessor_model: str,
        generator_model: str,
        max_output_tokens: int,
    ) -> None:
        if not assessor_model.strip() or not generator_model.strip():
            raise ValueError("Assessor and generator model names must not be blank.")
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive.")
        self._retriever = retriever
        self._provider = provider
        self._assessor_model = assessor_model
        self._generator_model = generator_model
        self._max_output_tokens = max_output_tokens

    def draft_reply(self, payload: SupportDraftRequest) -> SupportDraftResponse:
        started = time.perf_counter()
        trace_id = str(uuid4())
        route = route_question(payload.question)
        retrieval = self._retriever.retrieve(
            payload.question,
            top_k=self.retrieval_top_k,
        )
        retrieved_chunks = retrieval.hits

        if not retrieved_chunks:
            metadata = SupportDraftGenerationMetadata(
                outcome="no_retrieved_evidence",
                retrieved_chunk_count=0,
                retrieval_top_k=self.retrieval_top_k,
                total_elapsed_seconds=time.perf_counter() - started,
            )
            return self._response(
                trace_id=trace_id,
                route=route,
                model_used="none_no_retrieved_evidence",
                draft=(
                    "No verified support guidance was retrieved, so I cannot "
                    "provide an answer. A support agent must review this request."
                ),
                citations=[],
                assessment=None,
                metadata=metadata,
                escalation_reason="no_retrieved_evidence",
                review_triggers=["generated_pilot_review_first", "no_retrieved_evidence"],
            )

        assessor_system_prompt = build_evidence_assessor_system_prompt()
        assessor_user_prompt = build_evidence_assessor_user_prompt(
            question=payload.question,
            retrieved_chunks=retrieved_chunks,
        )
        assessor_generator = _MetricsStructuredGenerator(self._provider)
        assessor = OllamaEvidenceAssessor(
            generator=assessor_generator,
            model_name=self._assessor_model,
        )
        assessment_started = time.perf_counter()
        try:
            decision = assessor.assess(
                question=payload.question,
                retrieved_chunks=retrieved_chunks,
            )
        except EvidenceAssessorError as exc:
            cause = exc.__cause__
            diagnostic = (
                str(cause)
                if isinstance(cause, (EvidenceAssessmentValidationError, OllamaProviderError))
                else str(exc)
            )
            log_event(
                logger,
                "support_draft_assessment_failed",
                trace_id=trace_id,
                error_type=type(cause or exc).__name__,
                error_detail=diagnostic,
            )
            raise DraftGenerationError(
                "Evidence assessment failed; no customer response was generated."
            ) from exc
        assessor_elapsed = time.perf_counter() - assessment_started
        assessor_result = assessor_generator.result
        if assessor_result is None:
            raise DraftGenerationError(
                "Evidence assessment returned without a recorded model call."
            )
        _validate_generation_completion(
            metrics=assessor_result.metrics,
            output_limit=self.assessor_max_output_tokens,
            stage="evidence assessment",
        )

        citations = _assessment_citations(
            decision=decision,
            retrieved_chunks=retrieved_chunks,
        )
        assessment_payload = decision.model_dump(mode="json")
        review_triggers = ["generated_pilot_review_first"]
        if route.risk_level == "high":
            review_triggers.append("high_risk_intent")

        generator_model: str | None = None
        generator_system_hash: str | None = None
        generator_user_hash: str | None = None
        generator_schema_hash: str | None = None
        generator_elapsed: float | None = None
        generator_result: OllamaGenerationResult | None = None
        generator_completion_verified: bool | None = None
        escalation_reason = "generated_pilot_review_first"

        if decision.status in {"sufficient", "partial"}:
            system_prompt = build_customer_reply_system_prompt()
            user_prompt = build_customer_reply_user_prompt(
                question=payload.question,
                intent=route.intent,
                assessment=decision,
                retrieved_chunks=retrieved_chunks,
            )
            response_schema = GeneratedCustomerReply.model_json_schema()
            generator_started = time.perf_counter()
            try:
                generator_result = self._provider.generate_structured_with_metrics(
                    model_name=self._generator_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                    max_output_tokens=self._max_output_tokens,
                )
            except OllamaProviderError as exc:
                raise DraftGenerationError(
                    "Customer-response generation failed; no draft was saved."
                ) from exc
            generator_elapsed = time.perf_counter() - generator_started
            _validate_generation_completion(
                metrics=generator_result.metrics,
                output_limit=self._max_output_tokens,
                stage="customer response",
            )
            try:
                generated_reply = GeneratedCustomerReply.model_validate_json(
                    generator_result.text
                )
            except ValidationError as exc:
                raise DraftGenerationError(
                    "Customer-response generation returned malformed structured output."
                ) from exc
            draft = generated_reply.draft
            generator_model = self._generator_model
            generator_system_hash = _sha256_text(system_prompt)
            generator_user_hash = _sha256_text(user_prompt)
            generator_schema_hash = _sha256_schema(response_schema)
            generator_completion_verified = True
            outcome = "generated"
        elif decision.status == "clarification_needed":
            draft = (
                "Could you clarify this so I can help? "
                f"{decision.clarifying_question}"
            )
            review_triggers.append("clarification_needed")
            escalation_reason = "clarification_needed"
            outcome = "clarification_needed"
        elif decision.status == "insufficient":
            draft = (
                "The available support guidance does not determine the "
                "requested information. A support agent must review before "
                "providing an answer."
            )
            review_triggers.append("evidence_status_insufficient")
            escalation_reason = "evidence_status_insufficient"
            outcome = "insufficient_evidence"
        elif decision.status == "none":
            draft = (
                "The retrieved support passages do not answer this request. "
                "A support agent must review before responding."
            )
            review_triggers.append("evidence_status_none")
            escalation_reason = "evidence_status_none"
            outcome = "no_relevant_evidence"
        else:
            draft = (
                "The available support guidance conflicts on this point. "
                "A support agent must review before responding."
            )
            review_triggers.append("evidence_status_conflicting")
            escalation_reason = "evidence_status_conflicting"
            outcome = "conflicting_evidence"

        if decision.status == "partial":
            review_triggers.append("evidence_status_partial")
            escalation_reason = "evidence_status_partial"

        if generator_result is not None and not generator_result.text.strip():
            raise DraftGenerationError(
                "Customer-response generation returned empty text."
            )
        model_used = (
            f"assessor={self._assessor_model};generator={self._generator_model}"
            if generator_result is not None
            else f"assessor={self._assessor_model}"
        )
        metadata = SupportDraftGenerationMetadata(
            outcome=outcome,
            retrieved_chunk_count=len(retrieved_chunks),
            retrieval_top_k=self.retrieval_top_k,
            assessor_model=self._assessor_model,
            assessor_system_prompt_sha256=_sha256_text(assessor_system_prompt),
            assessor_user_prompt_sha256=_sha256_text(assessor_user_prompt),
            assessor_schema_sha256=_sha256_schema(
                EvidenceAssessmentProposal.model_json_schema()
            ),
            assessor_elapsed_seconds=assessor_elapsed,
            assessor_metrics=_call_metrics(assessor_result),
            generator_model=generator_model,
            generator_system_prompt_sha256=generator_system_hash,
            generator_user_prompt_sha256=generator_user_hash,
            generator_schema_sha256=generator_schema_hash,
            generator_elapsed_seconds=generator_elapsed,
            generator_metrics=(
                _call_metrics(generator_result)
                if generator_result is not None
                else None
            ),
            generator_max_output_tokens=(
                self._max_output_tokens
                if generator_result is not None
                else None
            ),
            generation_completion_verified=generator_completion_verified,
            total_elapsed_seconds=time.perf_counter() - started,
        )
        return self._response(
            trace_id=trace_id,
            route=route,
            model_used=model_used,
            draft=draft,
            citations=citations,
            assessment=assessment_payload,
            metadata=metadata,
            escalation_reason=escalation_reason,
            review_triggers=review_triggers,
        )

    @staticmethod
    def _response(
        *,
        trace_id: str,
        route: RoutingDecision,
        model_used: str,
        draft: str,
        citations: list[Citation],
        assessment: dict[str, object] | None,
        metadata: SupportDraftGenerationMetadata,
        escalation_reason: str,
        review_triggers: list[str],
    ) -> SupportDraftResponse:
        citation_source_ids = _unique_source_ids(citations)
        log_event(
            logger,
            "support_draft_generated",
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_used,
            generation_outcome=metadata.outcome,
            evidence_status=(
                assessment.get("status") if assessment is not None else None
            ),
            retrieved_chunk_count=metadata.retrieved_chunk_count,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason=escalation_reason,
            review_triggers=review_triggers,
            total_elapsed_seconds=metadata.total_elapsed_seconds,
        )
        return SupportDraftResponse(
            trace_id=trace_id,
            intent=route.intent,
            risk_level=route.risk_level,
            model_used=model_used,
            draft=draft,
            citations=citations,
            retrieval_confidence=None,
            answer_confidence=None,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason=escalation_reason,
            citation_source_ids=citation_source_ids,
            citation_contract_passed=bool(citation_source_ids),
            review_triggers=review_triggers,
            draft_mode="generated",
            evidence_assessment=assessment,
            generation_metadata=metadata,
        )
