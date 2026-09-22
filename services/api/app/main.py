import logging
import time
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from app.config import get_settings
from app.logging_utils import configure_logging, log_event
from app.llm_provider import StubLLMProvider
from app.orchestrator import CopilotOrchestrator
from app.review_workflow import apply_review_decision
from app.retriever import StubRetriever
from app.ingestion import IngestionPreviewPipeline
from app.schemas import (
    IngestionPreviewRequest,
    IngestionPreviewResponse,
    RetrievalHit,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    SupportDraftRequest,
    SupportDraftResponse,
    SupportReviewRequest,
    SupportReviewResponse,
)
from app.metrics import InMemoryMetrics
metrics = InMemoryMetrics()
app = FastAPI(title="Customer Support Copilot API", version="0.1.0")

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("support_copilot.api")
retriever = StubRetriever()
ingestion_preview_pipeline = IngestionPreviewPipeline()
orchestrator = CopilotOrchestrator(
    settings=settings,
    retriever=retriever,
    llm_provider=StubLLMProvider(),
)

@app.middleware("http")
async def request_lifecycle_logger(request: Request, call_next):
    request_id = str(uuid4())
    start = time.perf_counter()
    request.state.request_id = request_id

    log_event(
        logger,
        "request_started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    metrics.record_http_request(status_code=response.status_code, duration_ms=duration_ms)
    log_event(
        logger,
        "request_finished",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "support-copilot-api"}


@app.post("/v1/support/draft", response_model=SupportDraftResponse)
def draft_support_reply(payload: SupportDraftRequest) -> SupportDraftResponse:
    result = orchestrator.draft_reply(payload)
    metrics.record_support_draft(requires_human_review=result.requires_human_review)
    return result

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
@app.post("/v1/ingestion/preview", response_model=IngestionPreviewResponse)
def preview_ingestion(payload: IngestionPreviewRequest) -> IngestionPreviewResponse:
    return ingestion_preview_pipeline.preview(payload)

@app.post("/v1/support/review", response_model=SupportReviewResponse)
def review_support_draft(payload: SupportReviewRequest) -> SupportReviewResponse:
    try:
        return apply_review_decision(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/v1/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()