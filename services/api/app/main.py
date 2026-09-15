from fastapi import FastAPI

from app.config import get_settings
from app.llm_provider import StubLLMProvider
from app.orchestrator import CopilotOrchestrator
from app.retriever import StubRetriever
from app.schemas import (
    RetrievalHit,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    SupportDraftRequest,
    SupportDraftResponse,
)
app = FastAPI(title="Customer Support Copilot API", version="0.1.0")

settings = get_settings()
retriever = StubRetriever()
orchestrator = CopilotOrchestrator(
    settings=settings,
    retriever=retriever,
    llm_provider=StubLLMProvider(),
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "support-copilot-api"}


@app.post("/v1/support/draft", response_model=SupportDraftResponse)
def draft_support_reply(payload: SupportDraftRequest) -> SupportDraftResponse:
    return orchestrator.draft_reply(payload)

@app.post("/v1/retrieval/query", response_model=RetrievalQueryResponse)
def query_retrieval(payload: RetrievalQueryRequest) -> RetrievalQueryResponse:
    retrieval = retriever.retrieve(payload.question, top_k=payload.top_k)
    hits = [
        RetrievalHit(
            rank=index,
            source_id=citation.source_id,
            title=citation.title,
            excerpt=citation.excerpt,
        )
        for index, citation in enumerate(retrieval.citations, start=1)
    ]
    return RetrievalQueryResponse(
        query=payload.question,
        top_k=payload.top_k,
        retrieval_confidence=retrieval.confidence,
        hits=hits,
    )