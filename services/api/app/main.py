import logging
import time
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Request
from app.config import Settings, get_settings
from app.logging_utils import configure_logging, log_event
from app.orchestrator import (
    DraftGenerationError,
    GeneratedDraftOrchestrator,
    PreviewOnlyDraftOrchestrator,
)
from app.review_workflow import apply_review_decision
from app.retriever import PgVectorRetriever
from app.embedder import EmbeddingProviderError, OllamaEmbeddingProvider
from app.ingestion import (
    IngestionIndexPipeline,
    IngestionInputError,
    IngestionPreviewPipeline,
)
from app.ingestion_repository import IngestionVersionConflict, PostgresIngestionRepository
from app.persistence import (
    PersistenceError,
    PostgresSupportRepository,
    SupportDeliveryConflictError,
    SupportDraftNotFoundError,
    SupportRepository,
    SupportReviewConflictError,
)
from app.retrieval_repository import (
    PostgresRetrievalRepository,
    RetrievalIndexConfigurationError,
)
from app.llm_provider import OllamaLLMProvider
from app.llm_provider import DraftGenerationProvider
from app.reviewer_assistance import (
    AssessmentFeedbackRequest,
    RecordedAssessmentFeedback,
    ReviewerAssessmentRequest,
    ReviewerAssessmentResponse,
    ReviewerAssistanceConflictError,
    ReviewerAssistanceNotFoundError,
    ReviewerAssistanceService,
)
from app.reviewer_assistance_repository import PostgresReviewerAssistanceRepository
from app.schemas import (
    IngestionIndexRequest,
    IngestionIndexResponse,
    IngestionPreviewRequest,
    IngestionPreviewResponse,
    RetrievalHit,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    SupportDeliveryRequest,
    SupportDeliveryResponse,
    SupportDraftRequest,
    SupportDraftResponse,
    SupportReviewRequest,
    SupportReviewResponse,
)
from app.metrics import InMemoryMetrics
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
ingestion_preview_pipeline = IngestionPreviewPipeline()
embedding_provider = OllamaEmbeddingProvider(
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

def build_support_repository() -> SupportRepository:
    return PostgresSupportRepository(
        dsn=settings.postgres_dsn,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
    )


support_repository = build_support_repository()
ingestion_repository = PostgresIngestionRepository(
    dsn=settings.postgres_dsn,
    connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
)
retrieval_repository = PostgresRetrievalRepository(
    dsn=settings.postgres_dsn,
    connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
)
ingestion_index_pipeline = IngestionIndexPipeline(
    embedder=embedding_provider,
    repository=ingestion_repository,
)
retrieval_query_retriever = PgVectorRetriever(
    embedder=embedding_provider,
    repository=retrieval_repository,
)

def create_support_draft_orchestrator(
    *,
    app_settings: Settings,
    retriever: PgVectorRetriever,
    provider: DraftGenerationProvider,
) -> PreviewOnlyDraftOrchestrator | GeneratedDraftOrchestrator:
    if app_settings.support_draft_generation_enabled:
        return GeneratedDraftOrchestrator(
            retriever=retriever,
            provider=provider,
            assessor_model=app_settings.evidence_assessor_model,
            generator_model=app_settings.support_draft_generator_model,
            max_output_tokens=app_settings.support_draft_generation_max_tokens,
        )
    return PreviewOnlyDraftOrchestrator(retriever=retriever)


support_llm_provider = OllamaLLMProvider(
    base_url=settings.ollama_base_url,
    timeout_seconds=settings.ollama_timeout_seconds,
)
orchestrator = create_support_draft_orchestrator(
    app_settings=settings,
    retriever=retrieval_query_retriever,
    provider=support_llm_provider,
)
reviewer_assistance_service = ReviewerAssistanceService(
    repository=PostgresReviewerAssistanceRepository(
        dsn=settings.postgres_dsn,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
    ),
    provider=support_llm_provider,
    model_name=settings.evidence_assessor_model,
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
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DraftGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RetrievalIndexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        support_repository.save_support_draft(
            draft_request=payload,
            draft_response=result,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    metrics.record_support_draft(requires_human_review=result.requires_human_review)
    return result


@app.post("/v1/support/evidence-assessments", response_model=ReviewerAssessmentResponse)
def create_reviewer_assessment(payload: ReviewerAssessmentRequest) -> ReviewerAssessmentResponse:
    try:
        response = reviewer_assistance_service.create(payload)
    except (SupportDraftNotFoundError, ReviewerAssistanceNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewerAssistanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record = response.assessment
    if record.state == "running":
        raise HTTPException(status_code=409, detail={
            "assessment_id": str(record.assessment_id),
            "state": "running",
            "message": "This request ID is already running; read the saved assessment instead of retrying inference.",
        })
    if record.state == "failed":
        if record.error is None:
            raise HTTPException(status_code=503, detail="Saved assessment failure details are unavailable.")
        raise HTTPException(
            status_code=409 if record.error.code == "invalid_saved_evidence" else 502,
            detail={
                "assessment_id": str(record.assessment_id),
                "state": "failed",
                "error": record.error.model_dump(mode="json"),
            },
        )
    return response


@app.get("/v1/support/evidence-assessments/{assessment_id}", response_model=ReviewerAssessmentResponse)
def get_reviewer_assessment(assessment_id: UUID) -> ReviewerAssessmentResponse:
    try:
        return reviewer_assistance_service.get(assessment_id)
    except ReviewerAssistanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/v1/support/evidence-assessments/{assessment_id}/feedback",
    response_model=RecordedAssessmentFeedback,
)
def record_assessment_feedback(
    assessment_id: UUID, payload: AssessmentFeedbackRequest,
) -> RecordedAssessmentFeedback:
    try:
        return reviewer_assistance_service.record_feedback(assessment_id, payload)
    except ReviewerAssistanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewerAssistanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/retrieval/query", response_model=RetrievalQueryResponse)
def query_retrieval(payload: RetrievalQueryRequest) -> RetrievalQueryResponse:
    try:
        retrieval = retrieval_query_retriever.retrieve(
            payload.question,
            top_k=payload.top_k,
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RetrievalIndexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    hits = [
        RetrievalHit(
            rank=index,
            chunk_id=hit.chunk_id,
            source_id=hit.source_id,
            title=hit.title,
            policy_version=hit.policy_version,
            effective_date=hit.effective_date,
            access_scope=hit.access_scope,
            chunk_index=hit.chunk_index,
            section_path=hit.section_path,
            excerpt=hit.text,
            cosine_distance=hit.cosine_distance,
        )
        for index, hit in enumerate(retrieval.hits, start=1)
    ]
    return RetrievalQueryResponse(
        query=payload.question,
        top_k=payload.top_k,
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
    try:
        ai_draft = support_repository.get_pending_review_draft(trace_id=payload.trace_id)
    except SupportDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SupportReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        review_response = apply_review_decision(payload, ai_draft=ai_draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        support_repository.save_support_review(
            review_request=payload,
            ai_draft=ai_draft,
            review_response=review_response,
        )
    except SupportDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SupportReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return review_response


@app.post(
    "/v1/support/simulated-deliveries",
    response_model=SupportDeliveryResponse,
)
def simulate_support_delivery(
    payload: SupportDeliveryRequest,
) -> SupportDeliveryResponse:
    try:
        return support_repository.record_support_delivery(
            delivery_request=payload,
        )
    except SupportDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SupportDeliveryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()