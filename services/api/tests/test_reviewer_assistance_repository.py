import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import psycopg

from app.persistence import PersistenceError, SupportDraftNotFoundError
from app.reviewer_assistance import (
    AssessmentFailure,
    AssessmentFeedbackRequest,
    ReviewerAssistanceConflictError,
    ReviewerAssistanceNotFoundError,
    ReviewerAssessmentRequest,
)
from app.reviewer_assistance_repository import PostgresReviewerAssistanceRepository
from test_reviewer_assistance import finish_record, make_citation, make_record


class FakeCursor:
    def __init__(self, result_sets):
        self.results = iter(result_sets)
        self.rows = []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, parameters):
        self.executed.append((query, parameters))
        self.rows = next(self.results)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *args):
        self.committed = exc_type is None
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


class ReviewerAssistanceRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = PostgresReviewerAssistanceRepository(dsn="postgresql://test")
        self.request = ReviewerAssessmentRequest(
            trace_id="trace-1", request_id=uuid4(), reviewer_id="agent-1",
        )
        self.record = make_record(request=self.request, citations=[make_citation()])
        self.row = self.record.model_dump()

    def connect(self, result_sets):
        cursor = FakeCursor(result_sets)
        connection = FakeConnection(cursor)
        return connection, cursor

    def begin(self):
        return self.repository.begin_assessment(
            request=self.request, model_name="qwen3:4b",
            system_prompt_sha256="a" * 64, schema_sha256="b" * 64,
        )

    def test_new_attempt_is_reserved_and_committed_before_returning(self):
        connection, cursor = self.connect([
            [], [{"draft_mode": "preview_only"}],
            [{"assessment_id": self.request.request_id}], [self.row],
        ])
        with patch.object(self.repository, "_connect", return_value=connection):
            record, created = self.begin()
        self.assertTrue(created)
        self.assertEqual(record, self.record)
        self.assertTrue(connection.committed)
        insert_sql, parameters = cursor.executed[2]
        self.assertIn("ON CONFLICT (assessment_id) DO NOTHING", insert_sql)
        self.assertEqual(parameters[0], self.request.request_id)
        self.assertTrue(all("FOR UPDATE" not in query for query, _ in cursor.executed))

    def test_existing_attempt_reuses_its_id_without_writing(self):
        connection, cursor = self.connect([[self.row]])
        with patch.object(self.repository, "_connect", return_value=connection):
            record, created = self.begin()
        self.assertFalse(created)
        self.assertEqual(record.assessment_id, self.request.request_id)
        self.assertEqual(len(cursor.executed), 1)

    def test_concurrent_insert_loser_reads_the_winning_attempt(self):
        connection, cursor = self.connect([
            [], [{"draft_mode": "preview_only"}], [], [self.row],
        ])
        with patch.object(self.repository, "_connect", return_value=connection):
            record, created = self.begin()
        self.assertFalse(created)
        self.assertEqual(record.state, "running")
        self.assertTrue(connection.committed)

    def test_request_id_cannot_be_reused_for_a_different_trace_or_reviewer(self):
        for changed in ({"trace_id": "another-trace"}, {"reviewer_id": "another-agent"}):
            with self.subTest(changed=changed):
                connection, _ = self.connect([[{**self.row, **changed}]])
                with patch.object(self.repository, "_connect", return_value=connection):
                    with self.assertRaises(ReviewerAssistanceConflictError):
                        self.begin()

    def test_missing_or_non_preview_trace_does_not_reserve_an_attempt(self):
        for rows, error in (
            ([], SupportDraftNotFoundError),
            ([{"draft_mode": "generated"}], ReviewerAssistanceConflictError),
        ):
            with self.subTest(error=error.__name__):
                connection, cursor = self.connect([[], rows])
                with patch.object(self.repository, "_connect", return_value=connection):
                    with self.assertRaises(error):
                        self.begin()
                self.assertFalse(any("INSERT" in query for query, _ in cursor.executed))

    def test_terminal_failure_is_persisted_without_updating_draft_review_state(self):
        error = AssessmentFailure(code="assessor_failed", message="Invalid quote.")
        outcome = {
            "proposal": None, "error": error, "generation_metrics": None, "elapsed_seconds": 1.0,
        }
        failed = finish_record(self.record, **outcome)
        connection, cursor = self.connect([
            [{"assessment_id": self.request.request_id}], [failed.model_dump()],
        ])
        with patch.object(self.repository, "_connect", return_value=connection):
            result = self.repository.finish_assessment(assessment_id=self.request.request_id, **outcome)
        self.assertEqual(result.state, "failed")
        self.assertTrue(connection.committed)
        self.assertIn("AND state = 'running'", cursor.executed[0][0])
        self.assertFalse(any("UPDATE support_draft_events" in query for query, _ in cursor.executed))

    def test_terminal_outcomes_cannot_be_replaced(self):
        connection, _ = self.connect([[]])
        with patch.object(self.repository, "_connect", return_value=connection):
            with self.assertRaises(ReviewerAssistanceConflictError):
                self.repository.finish_assessment(
                    assessment_id=self.request.request_id, proposal=None,
                    error=AssessmentFailure(code="assessor_failed", message="Failed."),
                    generation_metrics=None, elapsed_seconds=1.0,
                )

    def test_missing_and_corrupt_records_are_explicit_errors(self):
        for rows, error in (([], ReviewerAssistanceNotFoundError), ([{"state": "completed"}], PersistenceError)):
            with self.subTest(error=error.__name__):
                connection, _ = self.connect([rows])
                with patch.object(self.repository, "_connect", return_value=connection):
                    with self.assertRaises(error):
                        self.repository.get_assessment(assessment_id=self.request.request_id)

    def feedback_row(self, feedback):
        return {
            **feedback.model_dump(),
            "assessment_id": self.request.request_id,
            "feedback_id": uuid4(),
            "created_at": datetime.now(timezone.utc),
        }

    def test_feedback_inserts_an_independent_event_without_approving_the_draft(self):
        feedback = AssessmentFeedbackRequest(
            reviewer_id="agent-1", verdict="needs_correction",
            reasons=["incorrect_status"], corrected_status="clarification_needed",
            notes="Customer scenario is unspecified.",
        )
        connection, cursor = self.connect([[{"state": "completed"}], [self.feedback_row(feedback)]])
        with patch.object(self.repository, "_connect", return_value=connection):
            result = self.repository.save_feedback(assessment_id=self.request.request_id, feedback=feedback)
        self.assertEqual(result.corrected_status, "clarification_needed")
        self.assertIn("FOR SHARE", cursor.executed[0][0])
        self.assertIn("INSERT INTO reviewer_assessment_feedback", cursor.executed[1][0])
        self.assertTrue(all("support_review_events" not in query for query, _ in cursor.executed))
        self.assertTrue(all("support_delivery_events" not in query for query, _ in cursor.executed))

    def test_identical_feedback_replay_returns_the_same_record(self):
        feedback = AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful")
        row = self.feedback_row(feedback)
        connection, _ = self.connect([[{"state": "completed"}], [], [row]])
        with patch.object(self.repository, "_connect", return_value=connection):
            result = self.repository.save_feedback(assessment_id=self.request.request_id, feedback=feedback)
        self.assertEqual(result.feedback_id, row["feedback_id"])
        self.assertTrue(connection.committed)

    def test_conflicting_feedback_is_not_overwritten(self):
        saved = AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful")
        changed = AssessmentFeedbackRequest(
            reviewer_id="agent-1", verdict="unusable",
            reasons=["unsupported_claim"], notes="The claim is not established.",
        )
        connection, cursor = self.connect([[{"state": "completed"}], [], [self.feedback_row(saved)]])
        with patch.object(self.repository, "_connect", return_value=connection):
            with self.assertRaises(ReviewerAssistanceConflictError):
                self.repository.save_feedback(assessment_id=self.request.request_id, feedback=changed)
        self.assertFalse(any("UPDATE" in query for query, _ in cursor.executed))
        self.assertFalse(connection.committed)

    def test_feedback_requires_a_terminal_assessment(self):
        for rows, error in (([], ReviewerAssistanceNotFoundError), ([{"state": "running"}], ReviewerAssistanceConflictError)):
            with self.subTest(error=error.__name__):
                connection, cursor = self.connect([rows])
                with patch.object(self.repository, "_connect", return_value=connection):
                    with self.assertRaises(error):
                        self.repository.save_feedback(
                            assessment_id=self.request.request_id,
                            feedback=AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful"),
                        )
                self.assertFalse(any("INSERT" in query for query, _ in cursor.executed))

    def test_failed_attempts_accept_only_explicit_failure_feedback(self):
        connection, _ = self.connect([[{"state": "failed"}]])
        with patch.object(self.repository, "_connect", return_value=connection):
            with self.assertRaises(ReviewerAssistanceConflictError):
                self.repository.save_feedback(
                    assessment_id=self.request.request_id,
                    feedback=AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful"),
                )
        feedback = AssessmentFeedbackRequest(
            reviewer_id="agent-1", verdict="unusable",
            reasons=["assessment_failed"], notes="Generation failed.",
        )
        connection, _ = self.connect([[{"state": "failed"}], [self.feedback_row(feedback)]])
        with patch.object(self.repository, "_connect", return_value=connection):
            result = self.repository.save_feedback(assessment_id=self.request.request_id, feedback=feedback)
        self.assertEqual(result.verdict, "unusable")

    def test_completed_attempt_cannot_be_labeled_as_an_assessment_failure(self):
        connection, _ = self.connect([[{"state": "completed"}]])
        with patch.object(self.repository, "_connect", return_value=connection):
            with self.assertRaises(ReviewerAssistanceConflictError):
                self.repository.save_feedback(
                    assessment_id=self.request.request_id,
                    feedback=AssessmentFeedbackRequest(
                        reviewer_id="agent-1", verdict="unusable",
                        reasons=["assessment_failed"], notes="Not a valid completed-attempt label.",
                    ),
                )

    def test_database_failure_is_reported_not_disguised_as_no_evidence(self):
        with patch.object(self.repository, "_connect", side_effect=psycopg.OperationalError("unavailable")):
            with self.assertRaises(PersistenceError):
                self.begin()


if __name__ == "__main__":
    unittest.main()
