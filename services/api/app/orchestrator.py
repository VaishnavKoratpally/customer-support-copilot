from uuid import uuid4

from app.config import Settings
from app.llm_provider import StubLLMProvider
from app.retriever import StubRetriever
from app.routing import route_question
from app.schemas import SupportDraftRequest, SupportDraftResponse


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

        model_name = self._settings.main_model
        escalation_reason: str | None = None
        if retrieval.confidence < self._settings.retrieval_confidence_threshold:
            model_name = self._settings.escalation_model
            escalation_reason = "low_retrieval_confidence"

        draft = self._llm_provider.draft_response(
            question=payload.question,
            intent=route.intent,
            model_name=model_name,
        )

        answer_confidence = round((retrieval.confidence * 0.7) + (0.2 if route.risk_level == "low" else 0.1), 2)

        requires_human_review = (
            route.risk_level == "high"
            or answer_confidence < self._settings.answer_confidence_threshold
            or len(retrieval.citations) == 0
        )
        if requires_human_review and escalation_reason is None:
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
        )

