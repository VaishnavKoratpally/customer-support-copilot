from uuid import uuid4

from app.config import Settings
from app.llm_provider import StubLLMProvider
from app.retriever import StubRetriever
from app.routing import route_question
from app.schemas import SupportDraftRequest, SupportDraftResponse
from app.prompts import build_support_system_prompt, build_support_user_prompt
from app.confidence import compute_answer_confidence
from app.review_policy import evaluate_review_policy

def _unique_source_ids(citations: list) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for citation in citations:
        source_id = citation.source_id
        if source_id not in seen:
            seen.add(source_id)
            ordered.append(source_id)
    return ordered

class CopilotOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        retriever: StubRetriever,
        llm_provider: StubLLMProvider,
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
        if "missing_citations" in review_decision.triggers:
            escalation_reason = "missing_citations"

        elif "low_answer_confidence" in review_decision.triggers and escalation_reason is None:
            escalation_reason = "policy_gate"

        elif "high_risk_intent" in review_decision.triggers and escalation_reason is None:
            escalation_reason = "policy_gate"

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
            escalation_reason=escalation_reason,
            citation_source_ids=citation_source_ids,
            citation_contract_passed=citation_contract_passed,
            review_triggers=review_decision.triggers,
        )

