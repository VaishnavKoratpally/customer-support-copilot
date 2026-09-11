from fastapi import FastAPI

from app.config import get_settings
from app.llm_provider import StubLLMProvider
from app.orchestrator import CopilotOrchestrator
from app.retriever import StubRetriever
from app.schemas import SupportDraftRequest, SupportDraftResponse

app = FastAPI(title="Customer Support Copilot API", version="0.1.0")

settings = get_settings()
orchestrator = CopilotOrchestrator(
    settings=settings,
    retriever=StubRetriever(),
    llm_provider=StubLLMProvider(),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "support-copilot-api"}


@app.post("/v1/support/draft", response_model=SupportDraftResponse)
def draft_support_reply(payload: SupportDraftRequest) -> SupportDraftResponse:
    return orchestrator.draft_reply(payload)

