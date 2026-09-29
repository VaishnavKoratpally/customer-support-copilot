from typing import Protocol
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.schemas import (
    SupportDraftRequest,
    SupportDraftResponse,
    SupportReviewRequest,
    SupportReviewResponse,
)


class PersistenceError(RuntimeError):
    pass


class SupportRepository(Protocol):
    def save_support_draft(
        self,
        *,
        draft_request: SupportDraftRequest,
        draft_response: SupportDraftResponse,
    ) -> None:
        ...

    def save_support_review(
        self,
        *,
        review_request: SupportReviewRequest,
        review_response: SupportReviewResponse,
    ) -> None:
        ...


class PostgresSupportRepository:
    def __init__(self, *, dsn: str, connect_timeout_seconds: float = 5.0) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout_seconds)

    def save_support_draft(
        self,
        *,
        draft_request: SupportDraftRequest,
        draft_response: SupportDraftResponse,
    ) -> None:
        citations_payload = [citation.model_dump(mode="json") for citation in draft_response.citations]
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO support_draft_events (
                            trace_id,
                            ticket_id,
                            question,
                            intent,
                            risk_level,
                            model_used,
                            draft,
                            citations,
                            retrieval_confidence,
                            answer_confidence,
                            requires_human_review,
                            escalation_reason,
                            citation_source_ids,
                            citation_contract_passed,
                            review_triggers
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            draft_response.trace_id,
                            draft_request.ticket_id,
                            draft_request.question,
                            draft_response.intent,
                            draft_response.risk_level,
                            draft_response.model_used,
                            draft_response.draft,
                            Jsonb(citations_payload),
                            draft_response.retrieval_confidence,
                            draft_response.answer_confidence,
                            draft_response.requires_human_review,
                            draft_response.escalation_reason,
                            Jsonb(draft_response.citation_source_ids),
                            draft_response.citation_contract_passed,
                            Jsonb(draft_response.review_triggers),
                        ),
                    )
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist support draft event: {exc}") from exc

    def save_support_review(
        self,
        *,
        review_request: SupportReviewRequest,
        review_response: SupportReviewResponse,
    ) -> None:
        review_id = str(uuid4())
        audit_payload = review_response.audit_event_payload.model_dump(mode="json")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO support_review_events (
                            id,
                            trace_id,
                            reviewer_id,
                            status,
                            ai_draft,
                            edited_draft,
                            final_draft,
                            rejection_reason_code,
                            requires_follow_up,
                            reviewed_at,
                            audit_event_payload
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            review_id,
                            review_response.trace_id,
                            review_response.reviewer_id,
                            review_response.status,
                            review_request.ai_draft,
                            review_request.edited_draft,
                            review_response.final_draft,
                            review_request.rejection_reason_code,
                            review_response.requires_follow_up,
                            review_response.reviewed_at,
                            Jsonb(audit_payload),
                        ),
                    )
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist support review event: {exc}") from exc
