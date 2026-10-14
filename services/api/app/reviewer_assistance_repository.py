from collections.abc import Mapping
from dataclasses import asdict
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.evidence_assessment import EvidenceAssessmentDecision
from app.llm_provider import OllamaGenerationMetrics
from app.persistence import PersistenceError, SupportDraftNotFoundError
from app.reviewer_assistance import (
    AssessmentFailure,
    AssessmentFeedbackRequest,
    RecordedAssessmentFeedback,
    RecordedReviewerAssessment,
    ReviewerAssessmentRequest,
    ReviewerAssistanceConflictError,
    ReviewerAssistanceNotFoundError,
)

_ASSESSMENT_SELECT = """
SELECT a.assessment_id, a.trace_id, a.reviewer_id, a.state, a.assessor_model,
    a.system_prompt_sha256, a.schema_sha256, a.proposed_assessment, a.error,
    a.generation_metrics, a.elapsed_seconds, a.started_at, a.completed_at,
    d.question, d.citations
FROM reviewer_assessment_events a
JOIN support_draft_events d ON d.trace_id = a.trace_id
WHERE a.assessment_id = %s
"""


class PostgresReviewerAssistanceRepository:
    def __init__(self, *, dsn: str, connect_timeout_seconds: float = 5.0) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _connect(self) -> psycopg.Connection[dict[str, object]]:
        return psycopg.connect(
            self._dsn, connect_timeout=self._connect_timeout_seconds, row_factory=dict_row,
        )

    @staticmethod
    def _assessment(row: Mapping[str, object] | None) -> RecordedReviewerAssessment:
        if row is None:
            raise ReviewerAssistanceNotFoundError("Reviewer assessment was not found.")
        try:
            return RecordedReviewerAssessment.model_validate(row)
        except ValidationError as exc:
            raise PersistenceError("Stored reviewer assessment is invalid.") from exc

    @staticmethod
    def _feedback(row: Mapping[str, object] | None) -> RecordedAssessmentFeedback:
        try:
            return RecordedAssessmentFeedback.model_validate(row)
        except ValidationError as exc:
            raise PersistenceError("Stored assessment feedback is invalid.") from exc

    @staticmethod
    def _check_request(record: RecordedReviewerAssessment, request: ReviewerAssessmentRequest) -> None:
        if record.trace_id != request.trace_id or record.reviewer_id != request.reviewer_id:
            raise ReviewerAssistanceConflictError("The assessment request ID belongs to a different request.")

    def begin_assessment(
        self, *, request: ReviewerAssessmentRequest, model_name: str,
        system_prompt_sha256: str, schema_sha256: str,
    ) -> tuple[RecordedReviewerAssessment, bool]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_ASSESSMENT_SELECT, (request.request_id,))
                    row = cur.fetchone()
                    if row is not None:
                        record = self._assessment(row)
                        self._check_request(record, request)
                        return record, False
                    cur.execute(
                        "SELECT draft_mode FROM support_draft_events WHERE trace_id = %s",
                        (request.trace_id,),
                    )
                    draft = cur.fetchone()
                    if draft is None:
                        raise SupportDraftNotFoundError("Support draft was not found.")
                    if draft["draft_mode"] != "preview_only":
                        raise ReviewerAssistanceConflictError("Reviewer assistance requires a preview-only trace.")
                    cur.execute(
                        """
                        INSERT INTO reviewer_assessment_events (
                            assessment_id, trace_id, reviewer_id, state, assessor_model,
                            system_prompt_sha256, schema_sha256
                        )
                        VALUES (%s, %s, %s, 'running', %s, %s, %s)
                        ON CONFLICT (assessment_id) DO NOTHING
                        RETURNING assessment_id
                        """,
                        (
                            request.request_id, request.trace_id, request.reviewer_id,
                            model_name, system_prompt_sha256, schema_sha256,
                        ),
                    )
                    created = cur.fetchone() is not None
                    cur.execute(_ASSESSMENT_SELECT, (request.request_id,))
                    record = self._assessment(cur.fetchone())
                    self._check_request(record, request)
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to reserve reviewer assessment: {exc}") from exc
        return record, created

    def finish_assessment(
        self, *, assessment_id: UUID, proposal: EvidenceAssessmentDecision | None,
        error: AssessmentFailure | None,
        generation_metrics: OllamaGenerationMetrics | None, elapsed_seconds: float,
    ) -> RecordedReviewerAssessment:
        if (proposal is None) == (error is None):
            raise ValueError("An assessment outcome must contain either a proposal or an error.")
        state = "completed" if error is None else "failed"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE reviewer_assessment_events
                        SET state = %s, proposed_assessment = %s, error = %s,
                            generation_metrics = %s, elapsed_seconds = %s, completed_at = NOW()
                        WHERE assessment_id = %s AND state = 'running'
                        RETURNING assessment_id
                        """,
                        (
                            state,
                            Jsonb(proposal.model_dump(mode="json")) if proposal is not None else None,
                            Jsonb(error.model_dump(mode="json")) if error is not None else None,
                            Jsonb(asdict(generation_metrics)) if generation_metrics is not None else None,
                            elapsed_seconds, assessment_id,
                        ),
                    )
                    if cur.fetchone() is None:
                        raise ReviewerAssistanceConflictError("Assessment is not running; its outcome cannot be replaced.")
                    cur.execute(_ASSESSMENT_SELECT, (assessment_id,))
                    record = self._assessment(cur.fetchone())
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist reviewer assessment outcome: {exc}") from exc
        return record

    def get_assessment(self, *, assessment_id: UUID) -> RecordedReviewerAssessment:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_ASSESSMENT_SELECT, (assessment_id,))
                    return self._assessment(cur.fetchone())
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to load reviewer assessment: {exc}") from exc

    def get_feedback(self, *, assessment_id: UUID) -> list[RecordedAssessmentFeedback]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT * FROM reviewer_assessment_feedback
                        WHERE assessment_id = %s ORDER BY created_at, feedback_id
                        """,
                        (assessment_id,),
                    )
                    return [self._feedback(row) for row in cur.fetchall()]
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to load assessment feedback: {exc}") from exc

    def save_feedback(
        self, *, assessment_id: UUID, feedback: AssessmentFeedbackRequest,
    ) -> RecordedAssessmentFeedback:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT state FROM reviewer_assessment_events WHERE assessment_id = %s FOR SHARE",
                        (assessment_id,),
                    )
                    assessment = cur.fetchone()
                    if assessment is None:
                        raise ReviewerAssistanceNotFoundError("Reviewer assessment was not found.")
                    if assessment["state"] == "running":
                        raise ReviewerAssistanceConflictError("Feedback requires a completed or failed assessment.")
                    if assessment["state"] == "failed":
                        if feedback.verdict != "unusable" or "assessment_failed" not in feedback.reasons:
                            raise ReviewerAssistanceConflictError("Failed assessments require unusable/assessment_failed feedback.")
                    elif "assessment_failed" in feedback.reasons:
                        raise ReviewerAssistanceConflictError("The assessment completed; it is not a failed attempt.")
                    cur.execute(
                        """
                        INSERT INTO reviewer_assessment_feedback (
                            feedback_id, assessment_id, reviewer_id, verdict, reasons, corrected_status, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (assessment_id, reviewer_id) DO NOTHING
                        RETURNING *
                        """,
                        (
                            uuid4(), assessment_id, feedback.reviewer_id, feedback.verdict,
                            Jsonb(feedback.reasons), feedback.corrected_status, feedback.notes,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute(
                            """
                            SELECT * FROM reviewer_assessment_feedback
                            WHERE assessment_id = %s AND reviewer_id = %s
                            """,
                            (assessment_id, feedback.reviewer_id),
                        )
                        record = self._feedback(cur.fetchone())
                        saved_request = AssessmentFeedbackRequest.model_validate(record.model_dump(
                            exclude={"feedback_id", "assessment_id", "created_at"},
                        ))
                        if saved_request != feedback:
                            raise ReviewerAssistanceConflictError("This reviewer already recorded different feedback for the attempt.")
                    else:
                        record = self._feedback(row)
                conn.commit()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist assessment feedback: {exc}") from exc
        return record
