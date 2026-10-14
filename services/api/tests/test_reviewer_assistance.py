import json
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.evidence_assessment import EvidenceAssessmentDecision
from app.llm_provider import OllamaGenerationMetrics, OllamaGenerationResult, OllamaLLMProvider, OllamaProviderError
from app.persistence import PersistenceError, SupportDraftNotFoundError
from app.reviewer_assistance import (
    AssessmentFailure,
    AssessmentFeedbackRequest,
    RecordedAssessmentFeedback,
    RecordedReviewerAssessment,
    ReviewerAssessmentRequest,
    ReviewerAssessmentResponse,
    ReviewerAssistanceConflictError,
    ReviewerAssistanceNotFoundError,
    ReviewerAssistanceRepository,
    ReviewerAssistanceService,
)
from app.schemas import Citation


def make_citation() -> Citation:
    return Citation(
        chunk_id=uuid4(),
        source_id="support-sla-02",
        title="Review policy",
        policy_version="v1",
        effective_date=date(2026, 10, 6),
        access_scope="internal",
        chunk_index=0,
        section_path="Initial review",
        excerpt="The initial review takes 2 business days.",
        cosine_distance=0.2,
    )


def make_record(*, request: ReviewerAssessmentRequest, citations: list[Citation]) -> RecordedReviewerAssessment:
    return RecordedReviewerAssessment(
        assessment_id=request.request_id,
        trace_id=request.trace_id,
        reviewer_id=request.reviewer_id,
        state="running",
        question="How long does the initial review take?",
        citations=citations,
        assessor_model="qwen3:4b",
        system_prompt_sha256="a" * 64,
        schema_sha256="b" * 64,
        proposed_assessment=None,
        error=None,
        generation_metrics=None,
        elapsed_seconds=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )


def finish_record(record: RecordedReviewerAssessment, **outcome) -> RecordedReviewerAssessment:
    return RecordedReviewerAssessment.model_validate({
        **record.model_dump(),
        "state": "failed" if outcome["error"] is not None else "completed",
        "proposed_assessment": outcome["proposal"],
        "error": outcome["error"],
        "generation_metrics": outcome["generation_metrics"],
        "elapsed_seconds": outcome["elapsed_seconds"],
        "completed_at": datetime.now(timezone.utc),
    })


class ReviewerAssistanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.request = ReviewerAssessmentRequest(
            trace_id="trace-1", request_id=uuid4(), reviewer_id="agent-1",
        )
        self.citation = make_citation()
        self.record = make_record(request=self.request, citations=[self.citation])
        self.repository = Mock(spec=ReviewerAssistanceRepository)
        self.repository.begin_assessment.return_value = (self.record, True)
        self.repository.get_feedback.return_value = []
        self.repository.finish_assessment.side_effect = (
            lambda **kwargs: finish_record(self.record, **kwargs)
        )
        self.provider = Mock(spec=OllamaLLMProvider)
        self.proposal = {
            "requested_information": [{
                "requested_information": "initial review duration",
                "finding": "supported",
                "answer": "The initial review takes 2 business days.",
                "evidence": [{
                    "chunk_id": str(self.citation.chunk_id),
                    "quote": self.citation.excerpt,
                }],
            }],
            "supporting_facts": [],
            "clarifying_question": None,
        }
        self.metrics = OllamaGenerationMetrics(
            total_duration_ns=3_000_000_000,
            load_duration_ns=0,
            prompt_eval_count=1000,
            prompt_eval_duration_ns=100_000_000,
            eval_count=200,
            eval_duration_ns=2_900_000_000,
            done_reason="stop",
        )
        self.set_provider_output(self.proposal)
        self.service = ReviewerAssistanceService(
            repository=self.repository,
            provider=self.provider,
            model_name="qwen3:4b",
        )

    def set_provider_output(self, proposal):
        self.provider.generate_structured_with_metrics.return_value = OllamaGenerationResult(
            text=json.dumps(proposal), metrics=self.metrics,
        )

    def test_assesses_only_saved_evidence_once_and_returns_an_advisory_proposal(self):
        response = self.service.create(self.request)

        self.provider.generate_structured_with_metrics.assert_called_once()
        payload = self.provider.generate_structured_with_metrics.call_args.kwargs
        self.assertEqual(payload["model_name"], "qwen3:4b")
        user_input = json.loads(payload["user_prompt"].split("\n", 1)[1])
        self.assertEqual(user_input["question"], self.record.question)
        self.assertEqual(user_input["retrieved_chunks"][0]["text"], self.citation.excerpt)
        self.assertEqual(user_input["retrieved_chunks"][0]["chunk_id"], str(self.citation.chunk_id))
        self.assertNotIn("cosine_distance", user_input["retrieved_chunks"][0])
        self.assertEqual(response.assessment.state, "completed")
        self.assertEqual(response.assessment.proposed_assessment.status, "sufficient")
        self.assertEqual(response.assessment.generation_metrics, self.metrics)
        self.assertTrue(response.advisory_only)
        self.assertIn("Unverified", response.notice)
        self.assertEqual(response.assessment.citations, [self.citation])
        self.assertNotIn("draft", response.model_dump())
        reservation = self.repository.begin_assessment.call_args.kwargs
        self.assertEqual(len(reservation["system_prompt_sha256"]), 64)
        self.assertEqual(len(reservation["schema_sha256"]), 64)

    def test_replayed_completed_request_returns_the_same_outcome_without_inference(self):
        completed = self.service.create(self.request).assessment
        self.provider.reset_mock()
        self.repository.finish_assessment.reset_mock()
        self.repository.begin_assessment.return_value = (completed, False)

        response = self.service.create(self.request)

        self.assertEqual(response.assessment, completed)
        self.provider.generate_structured_with_metrics.assert_not_called()
        self.repository.finish_assessment.assert_not_called()

    def test_replayed_running_request_does_not_issue_another_call(self):
        self.repository.begin_assessment.return_value = (self.record, False)

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "running")
        self.provider.generate_structured_with_metrics.assert_not_called()

    def test_a_new_request_id_deliberately_creates_another_attempt(self):
        new_request = ReviewerAssessmentRequest(
            trace_id=self.request.trace_id, request_id=uuid4(), reviewer_id=self.request.reviewer_id,
        )
        new_record = make_record(request=new_request, citations=[self.citation])
        self.repository.begin_assessment.side_effect = [(self.record, True), (new_record, True)]
        self.repository.finish_assessment.side_effect = lambda **kwargs: finish_record(
            self.record if kwargs["assessment_id"] == self.request.request_id else new_record,
            **kwargs,
        )

        first = self.service.create(self.request)
        second = self.service.create(new_request)

        self.assertNotEqual(first.assessment.assessment_id, second.assessment.assessment_id)
        self.assertEqual(self.provider.generate_structured_with_metrics.call_count, 2)

    def test_provenance_checks_do_not_turn_the_proposal_into_an_authorization(self):
        self.proposal["requested_information"][0]["answer"] = "The initial review takes 20 business days."
        self.set_provider_output(self.proposal)

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "completed")
        self.assertTrue(response.advisory_only)
        self.assertIn("Unverified", response.notice)

    def test_invalid_quotes_or_chunk_ids_are_recorded_as_failed_not_supported(self):
        for reference in (
            {"chunk_id": str(uuid4()), "quote": self.citation.excerpt},
            {"chunk_id": str(self.citation.chunk_id), "quote": "The review takes 10 days."},
        ):
            with self.subTest(reference=reference):
                self.proposal["requested_information"][0]["evidence"] = [reference]
                self.set_provider_output(self.proposal)

                response = self.service.create(self.request)

                self.assertEqual(response.assessment.state, "failed")
                self.assertIsNone(response.assessment.proposed_assessment)
                self.assertEqual(response.assessment.error.code, "assessor_failed")
                self.assertEqual(response.assessment.generation_metrics, self.metrics)
                self.assertIn("quote validation", response.assessment.error.message)

    def test_provider_failure_is_recorded_and_reusing_its_id_does_not_retry(self):
        self.provider.generate_structured_with_metrics.side_effect = OllamaProviderError("timed out")

        failed = self.service.create(self.request).assessment

        self.assertEqual(failed.state, "failed")
        self.assertEqual(failed.error.code, "assessor_failed")
        self.assertIsNone(failed.generation_metrics)
        self.repository.begin_assessment.return_value = (failed, False)
        self.service.create(self.request)
        self.provider.generate_structured_with_metrics.assert_called_once()

    def test_schema_invalid_output_is_recorded_as_failure(self):
        self.set_provider_output({
            "requested_information": [],
            "supporting_facts": [],
            "clarifying_question": None,
        })

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "failed")
        self.assertIn("invalid evidence assessment proposal", response.assessment.error.message)

    def test_missing_saved_provenance_fails_without_calling_the_model(self):
        self.citation.chunk_id = None

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "failed")
        self.assertEqual(response.assessment.error.code, "invalid_saved_evidence")
        self.provider.generate_structured_with_metrics.assert_not_called()
        self.repository.finish_assessment.assert_called_once()

    def test_duplicate_saved_chunk_ids_fail_without_inference(self):
        self.record.citations.append(self.citation)

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.error.code, "invalid_saved_evidence")
        self.provider.generate_structured_with_metrics.assert_not_called()

    def test_invalid_saved_metadata_fails_explicitly_before_inference(self):
        for changed in (
            {"cosine_distance": float("nan")}, {"chunk_index": -1},
            {"excerpt": " "}, {"policy_version": None}, {"effective_date": None},
        ):
            with self.subTest(changed=changed):
                citation = make_citation()
                for field, value in changed.items():
                    setattr(citation, field, value)
                self.record.citations = [citation]

                response = self.service.create(self.request)

                self.assertEqual(response.assessment.state, "failed")
                self.assertEqual(response.assessment.error.code, "invalid_saved_evidence")
                self.provider.generate_structured_with_metrics.assert_not_called()

    def test_empty_saved_evidence_does_not_allow_an_invented_quote(self):
        self.record.citations = []

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "failed")
        self.assertIsNone(response.assessment.proposed_assessment)

    def test_empty_saved_evidence_can_record_an_explicit_no_evidence_proposal(self):
        self.record.citations = []
        self.set_provider_output({
            "requested_information": [{
                "requested_information": "initial review duration",
                "finding": "no_relevant_evidence", "answer": None, "evidence": [],
            }],
            "supporting_facts": [], "clarifying_question": None,
        })

        response = self.service.create(self.request)

        self.assertEqual(response.assessment.state, "completed")
        self.assertEqual(response.assessment.proposed_assessment.status, "none")

    def test_reservation_or_outcome_persistence_failure_never_returns_success(self):
        self.repository.begin_assessment.side_effect = PersistenceError("database unavailable")
        with self.assertRaises(PersistenceError):
            self.service.create(self.request)
        self.provider.generate_structured_with_metrics.assert_not_called()
        self.repository.begin_assessment.side_effect = None
        self.repository.finish_assessment.side_effect = PersistenceError("write failed")
        with self.assertRaises(PersistenceError):
            self.service.create(self.request)

    def test_get_and_feedback_delegate_to_persistence_without_inference(self):
        self.repository.get_assessment.return_value = self.record
        feedback = AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful")

        self.service.get(self.record.assessment_id)
        self.service.record_feedback(self.record.assessment_id, feedback)

        self.repository.get_assessment.assert_called_once_with(assessment_id=self.record.assessment_id)
        self.repository.save_feedback.assert_called_once_with(
            assessment_id=self.record.assessment_id, feedback=feedback,
        )
        self.provider.generate_structured_with_metrics.assert_not_called()


class ReviewerAssistanceContractTests(unittest.TestCase):
    def test_request_requires_an_explicit_valid_uuid(self):
        for fields in ({}, {"request_id": "not-a-uuid"}):
            with self.subTest(fields=fields):
                with self.assertRaises(ValidationError):
                    ReviewerAssessmentRequest(trace_id="trace-1", reviewer_id="agent-1", **fields)

    def test_request_cannot_replace_the_saved_question_or_evidence(self):
        for injected in ({"question": "Injected question"}, {"citations": []}, {"approve": True}):
            with self.subTest(field=injected):
                with self.assertRaises(ValidationError):
                    ReviewerAssessmentRequest(
                        trace_id="trace-1", request_id=uuid4(), reviewer_id="agent-1", **injected,
                    )

    def test_corrective_feedback_requires_explicit_reasons_and_notes(self):
        with self.assertRaises(ValidationError):
            AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="needs_correction")
        feedback = AssessmentFeedbackRequest(
            reviewer_id="agent-1",
            verdict="needs_correction",
            reasons=["incorrect_status"],
            corrected_status="clarification_needed",
            notes="The customer did not specify which account-access problem applies.",
        )
        self.assertEqual(feedback.corrected_status, "clarification_needed")

    def test_feedback_rejects_conflicting_or_duplicate_corrections(self):
        invalid = (
            {"verdict": "helpful", "reasons": ["unsupported_claim"]},
            {"verdict": "needs_correction", "reasons": ["irrelevant_fact"], "corrected_status": "none", "notes": "Wrong status."},
            {"verdict": "unusable", "reasons": ["assessment_failed", "assessment_failed"], "notes": "Failure."},
            {"verdict": "needs_correction", "reasons": ["assessment_failed"], "notes": "Failure."},
            {"verdict": "unusable", "reasons": ["unsupported_claim"], "notes": "  "},
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(ValidationError):
                    AssessmentFeedbackRequest(reviewer_id="agent-1", **fields)

    def test_feedback_is_not_a_draft_review_or_delivery_request(self):
        with self.assertRaises(ValidationError):
            AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful", status="approve")

    def test_recorded_outcome_requires_the_proposal_or_the_explicit_error(self):
        request = ReviewerAssessmentRequest(trace_id="trace-1", request_id=uuid4(), reviewer_id="agent-1")
        record = make_record(request=request, citations=[])
        for changed in (
            {"state": "completed", "completed_at": datetime.now(timezone.utc), "elapsed_seconds": 1.0},
            {"state": "failed", "completed_at": datetime.now(timezone.utc), "elapsed_seconds": 1.0},
            {"generation_metrics": OllamaGenerationMetrics(
                total_duration_ns=None, load_duration_ns=None,
                prompt_eval_count=None, prompt_eval_duration_ns=None,
                eval_count=1, eval_duration_ns=None, done_reason=None,
            )},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValidationError):
                    RecordedReviewerAssessment.model_validate({**record.model_dump(), **changed})


class ReviewerAssistanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.request = ReviewerAssessmentRequest(
            trace_id="trace-1", request_id=uuid4(), reviewer_id="agent-1",
        )
        self.record = make_record(request=self.request, citations=[make_citation()])
        self.service = Mock(spec=ReviewerAssistanceService)

    def call_create(self):
        with patch.object(main, "reviewer_assistance_service", self.service):
            return main.create_reviewer_assessment(self.request)

    def test_completed_assistance_does_not_approve_or_deliver_the_preview(self):
        proposal = EvidenceAssessmentDecision(
            status="none", action="abstain_and_escalate",
            requested_information=[], supporting_facts=[],
        )
        record = finish_record(
            self.record, proposal=proposal, error=None, generation_metrics=None, elapsed_seconds=1.0,
        )
        self.service.create.return_value = ReviewerAssessmentResponse(assessment=record, feedback=[])
        with (
            patch.object(main, "support_repository") as drafts,
            patch.object(main, "orchestrator") as orchestrator,
        ):
            response = self.call_create()
        self.assertTrue(response.advisory_only)
        self.assertFalse(drafts.mock_calls)
        self.assertFalse(orchestrator.mock_calls)

    def test_running_request_returns_conflict_with_assessment_id(self):
        self.service.create.return_value = ReviewerAssessmentResponse(assessment=self.record, feedback=[])
        with self.assertRaises(HTTPException) as raised:
            self.call_create()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["assessment_id"], str(self.request.request_id))

    def test_failed_assessment_surfaces_an_error_with_a_retrievable_id(self):
        for code, http_status in (("assessor_failed", 502), ("invalid_saved_evidence", 409)):
            with self.subTest(code=code):
                record = finish_record(
                    self.record, proposal=None,
                    error=AssessmentFailure(code=code, message="Assessment unavailable."),
                    generation_metrics=None, elapsed_seconds=1.0,
                )
                self.service.create.return_value = ReviewerAssessmentResponse(assessment=record, feedback=[])
                with self.assertRaises(HTTPException) as raised:
                    self.call_create()
                self.assertEqual(raised.exception.status_code, http_status)
                self.assertEqual(raised.exception.detail["state"], "failed")
                self.assertEqual(raised.exception.detail["assessment_id"], str(self.request.request_id))

    def test_creation_maps_missing_traces_conflicts_and_persistence_errors(self):
        failures = (
            (SupportDraftNotFoundError("Missing trace."), 404),
            (ReviewerAssistanceConflictError("Request ID collision."), 409),
            (PersistenceError("Database unavailable."), 503),
        )
        for failure, status in failures:
            with self.subTest(failure=type(failure).__name__):
                self.service.create.side_effect = failure
                with self.assertRaises(HTTPException) as raised:
                    self.call_create()
                self.assertEqual(raised.exception.status_code, status)

    def test_saved_failed_state_can_be_inspected_without_changing_it(self):
        record = finish_record(
            self.record, proposal=None,
            error=AssessmentFailure(code="assessor_failed", message="Invalid quote."),
            generation_metrics=None, elapsed_seconds=1.0,
        )
        self.service.get.return_value = ReviewerAssessmentResponse(assessment=record, feedback=[])
        with patch.object(main, "reviewer_assistance_service", self.service):
            response = main.get_reviewer_assessment(self.request.request_id)
        self.assertEqual(response.assessment.state, "failed")
        self.assertIsNone(response.assessment.proposed_assessment)

    def test_feedback_does_not_call_draft_review_or_delivery(self):
        payload = AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful")
        feedback = RecordedAssessmentFeedback(
            **payload.model_dump(),
            feedback_id=uuid4(), assessment_id=self.request.request_id,
            created_at=datetime.now(timezone.utc),
        )
        self.service.record_feedback.return_value = feedback
        with (
            patch.object(main, "reviewer_assistance_service", self.service),
            patch.object(main, "support_repository") as drafts,
            patch.object(main, "review_idempotency_store") as idempotency,
        ):
            response = main.record_assessment_feedback(self.request.request_id, payload)
        self.assertEqual(response, feedback)
        self.assertFalse(drafts.mock_calls)
        self.assertFalse(idempotency.mock_calls)

    def test_read_and_feedback_map_missing_assessments_and_database_errors(self):
        for failure, status in (
            (ReviewerAssistanceNotFoundError("Missing assessment."), 404),
            (PersistenceError("Database unavailable."), 503),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.service.get.side_effect = failure
                self.service.record_feedback.side_effect = failure
                with patch.object(main, "reviewer_assistance_service", self.service):
                    with self.assertRaises(HTTPException) as read_error:
                        main.get_reviewer_assessment(self.request.request_id)
                    with self.assertRaises(HTTPException) as feedback_error:
                        main.record_assessment_feedback(
                            self.request.request_id,
                            AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful"),
                        )
                self.assertEqual(read_error.exception.status_code, status)
                self.assertEqual(feedback_error.exception.status_code, status)

    def test_feedback_conflicts_return_409(self):
        self.service.record_feedback.side_effect = ReviewerAssistanceConflictError("Feedback already recorded.")
        with patch.object(main, "reviewer_assistance_service", self.service):
            with self.assertRaises(HTTPException) as raised:
                main.record_assessment_feedback(
                    self.request.request_id,
                    AssessmentFeedbackRequest(reviewer_id="agent-1", verdict="helpful"),
                )
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
