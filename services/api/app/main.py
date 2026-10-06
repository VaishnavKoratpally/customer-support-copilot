import logging
import time
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from app.config import get_settings
from app.logging_utils import configure_logging, log_event
from app.orchestrator import CopilotOrchestrator
from app.review_workflow import apply_review_decision
from app.retriever import StubRetriever
from app.embedder import EmbeddingProviderError, OllamaEmbeddingProvider
from app.ingestion import (
    IngestionIndexPipeline,
    IngestionInputError,
    IngestionPreviewPipeline,
)
from app.ingestion_repository import IngestionVersionConflict, PostgresIngestionRepository
from app.persistence import PersistenceError, PostgresSupportRepository, SupportRepository
from app.schemas import (
    IngestionIndexRequest,
    IngestionIndexResponse,
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
from app.llm_provider import LLMProvider, OllamaLLMProvider, StubLLMProvider
from redis import Redis
from app.idempotency import (
    IdempotencyUnavailableError,
    RedisIdempotencyStore,
    review_idempotency_key,
)

metrics = InMemoryMetrics()
app = FastAPI(title="Customer Support Copilot API", version="0.1.0")

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("support_copilot.api")
retriever = StubRetriever()
ingestion_preview_pipeline = IngestionPreviewPipeline()
ingestion_embedding_provider = OllamaEmbeddingProvider(
    base_url=settings.ollama_base_url,
    model_name=settings.embedding_model,
    timeout_seconds=settings.embedding_timeout_seconds,
)

def build_review_idempotency_store() -> RedisIdempotencyStore:
    redis_client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True,
    )
    return RedisIdempotencyStore(
        client=redis_client,
        ttl_seconds=settings.redis_idempotency_ttl_seconds,
    )
review_idempotency_store = build_review_idempotency_store()

def build_llm_provider() -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaLLMProvider(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if settings.llm_provider == "stub":
        return StubLLMProvider()
    raise ValueError(f"Unsupported llm_provider: {settings.llm_provider}")


def build_support_repository() -> SupportRepository:
    return PostgresSupportRepository(
        dsn=settings.postgres_dsn,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
    )


llm_provider = build_llm_provider()
support_repository = build_support_repository()
ingestion_repository = PostgresIngestionRepository(
    dsn=settings.postgres_dsn,
    connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
)
ingestion_index_pipeline = IngestionIndexPipeline(
    embedder=ingestion_embedding_provider,
    repository=ingestion_repository,
)

orchestrator = CopilotOrchestrator(
    settings=settings,
    retriever=retriever,
    llm_provider=llm_provider,
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

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        metrics.record_http_request(
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
        )
        log_event(
            logger,
            "request_finished",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    metrics.record_http_request(
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
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
    try:
        result = orchestrator.draft_reply(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        support_repository.save_support_draft(
            draft_request=payload,
            draft_response=result,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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


@app.post("/v1/ingestion/index", response_model=IngestionIndexResponse)
def index_ingestion(payload: IngestionIndexRequest) -> IngestionIndexResponse:
    try:
        return ingestion_index_pipeline.index(payload)
    except IngestionVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IngestionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/support/review", response_model=SupportReviewResponse)
def review_support_draft(payload: SupportReviewRequest) -> SupportReviewResponse:
    idempotency_key = review_idempotency_key(payload)
    try:
        claimed = review_idempotency_store.claim(key=idempotency_key)
    except IdempotencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not claimed:
        raise HTTPException(
            status_code=409,
            detail="Duplicate review request detected; request already processed.",
        )
    try:
        review_response = apply_review_decision(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        support_repository.save_support_review(
            review_request=payload,
            review_response=review_response,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return review_response

@app.get("/v1/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()