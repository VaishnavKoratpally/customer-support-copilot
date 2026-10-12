from hashlib import sha256
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


class SupportDraftNotFoundError(LookupError):
    pass


class SupportReviewConflictError(RuntimeError):
    pass


class SupportRepository(Protocol):
    def save_support_draft(
        self,
        *,
        draft_request: SupportDraftRequest,
        draft_response: SupportDraftResponse,
    ) -> None:
        ...

    def get_pending_review_draft(self, *, trace_id: str) -> str:
        ...

    def save_support_review(
        self,
        *,
        review_request: SupportReviewRequest,
        ai_draft: str,
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
                            review_status,
                            escalation_reason,
                            citation_source_ids,
                            citation_contract_passed,
                            review_triggers
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                            draft_response.review_status,
                            draft_response.escalation_reason,
                            Jsonb(draft_response.citation_source_ids),
                            draft_response.citation_contract_passed,
                            Jsonb(draft_response.review_triggers),
                        ),
                    )
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist support draft event: {exc}") from exc

    def get_pending_review_draft(self, *, trace_id: str) -> str:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT draft, requires_human_review, review_status
                        FROM support_draft_events
                        WHERE trace_id = %s
                        """,
                        (trace_id,),
                    )
                    row = cur.fetchone()
        except psycopg.Error as exc:
            raise PersistenceError(
                f"Failed to load support draft for review: {exc}"
            ) from exc

        if row is None:
            raise SupportDraftNotFoundError("Support draft was not found.")
        if not row[1] or row[2] != "pending_review":
            raise SupportReviewConflictError(
                "Support draft is not awaiting human review."
            )
        return row[0]

    def save_support_review(
        self,
        *,
        review_request: SupportReviewRequest,
        ai_draft: str,
        review_response: SupportReviewResponse,
    ) -> None:
        expected_review_status = {
            "approve": "approved",
            "edit": "edited",
            "reject": "rejected",
        }[review_request.status]
        audit_event_payload = review_response.audit_event_payload
        if (
            review_request.trace_id != review_response.trace_id
            or review_request.reviewer_id != review_response.reviewer_id
            or review_request.status != review_response.status
            or review_response.review_status != expected_review_status
            or audit_event_payload.trace_id != review_request.trace_id
            or audit_event_payload.status != review_request.status
        ):
            raise SupportReviewConflictError(
                "Review response does not match the review request."
            )

        review_id = str(uuid4())
        audit_payload = audit_event_payload.model_dump(mode="json")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT draft, requires_human_review, review_status
                        FROM support_draft_events
                        WHERE trace_id = %s
                        FOR UPDATE
                        """,
                        (review_request.trace_id,),
                    )
                    draft_row = cur.fetchone()
                    if draft_row is None:
                        raise SupportDraftNotFoundError("Support draft was not found.")

                    stored_draft, requires_human_review, current_status = draft_row
                    if not requires_human_review or current_status != "pending_review":
                        raise SupportReviewConflictError(
                            "Support draft is no longer awaiting human review."
                        )
                    if (
                        stored_draft != ai_draft
                        or sha256(stored_draft.encode("utf-8")).hexdigest()
                        != audit_event_payload.ai_draft_sha256
                    ):
                        raise SupportReviewConflictError(
                            "Review decision does not match the persisted draft."
                        )

                    final_draft_hash = (
                        sha256(review_response.final_draft.encode("utf-8")).hexdigest()
                        if review_response.final_draft
                        else None
                    )
                    if final_draft_hash != audit_event_payload.final_draft_sha256:
                        raise SupportReviewConflictError(
                            "Review response final draft hash is invalid."
                        )

                    cur.execute(
                        """
                        UPDATE support_draft_events
                        SET review_status = %s
                        WHERE trace_id = %s
                          AND requires_human_review = TRUE
                          AND review_status = 'pending_review'
                        """,
                        (review_response.review_status, review_request.trace_id),
                    )
                    if cur.rowcount != 1:
                        raise SupportReviewConflictError(
                            "Support draft is no longer awaiting human review."
                        )

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
                            stored_draft,
                            review_request.edited_draft,
                            review_response.final_draft,
                            review_request.rejection_reason_code,
                            review_response.requires_follow_up,
                            review_response.reviewed_at,
                            Jsonb(audit_payload),
                        ),
                    )
                conn.commit()
        except (SupportDraftNotFoundError, SupportReviewConflictError):
            raise
        except psycopg.Error as exc:
            raise PersistenceError(
                f"Failed to persist support review event: {exc}"
            ) from exc
