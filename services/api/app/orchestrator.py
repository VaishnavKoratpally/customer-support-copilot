from uuid import uuid4
import logging
from app.logging_utils import log_event
from app.config import Settings
from app.retriever import PgVectorRetriever, StubRetriever
from app.routing import route_question
from app.schemas import Citation, DraftReviewStatus, SupportDraftRequest, SupportDraftResponse
from app.prompts import build_support_system_prompt, build_support_user_prompt
from app.confidence import compute_answer_confidence
from app.review_policy import evaluate_review_policy
from app.llm_provider import LLMProvider

logger = logging.getLogger("support_copilot.orchestrator")

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
