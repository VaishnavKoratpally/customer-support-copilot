import unittest
from uuid import uuid4
from unittest.mock import patch

from app.persistence import PostgresSupportRepository
from app.schemas import (
    FAQAutomationEligibility,
    FAQFinalResponseChecks,
    SupportDraftGenerationMetadata,
    SupportDraftRequest,
    SupportDraftResponse,
)


class FakeCursor:
    def __init__(self) -> None:
        self.query: str | None = None
        self.parameters: tuple[object, ...] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self.query = query
        self.parameters = parameters


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


class SupportDraftGenerationPersistenceTests(unittest.TestCase):
    def test_generated_response_assessment_and_metadata_are_persisted(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        draft = SupportDraftResponse(
            trace_id=str(uuid4()),
            intent="general_support",
            risk_level="low",
            model_used="assessor=qwen3:4b;generator=qwen3:4b",
            draft="An evidence-backed draft.",
            citations=[],
            retrieval_confidence=None,
            answer_confidence=None,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason="generated_pilot_review_first",
            citation_source_ids=[],
            citation_contract_passed=False,
            review_triggers=["generated_pilot_review_first"],
            evidence_assessment={
                "status": "sufficient",
                "action": "draft_from_determined_claims",
                "requested_information": [],
                "supporting_facts": [],
            },
            generation_metadata=SupportDraftGenerationMetadata(
                outcome="generated",
                retrieved_chunk_count=1,
                retrieval_top_k=3,
                assessor_model="qwen3:4b",
                assessor_system_prompt_sha256="a" * 64,
                assessor_user_prompt_sha256="b" * 64,
                assessor_schema_sha256="c" * 64,
                assessor_elapsed_seconds=0.8,
                generator_model="qwen3:4b",
                generator_system_prompt_sha256="d" * 64,
                generator_user_prompt_sha256="e" * 64,
                generator_schema_sha256="f" * 64,
                generator_elapsed_seconds=0.5,
                generator_max_output_tokens=256,
                generation_completion_verified=True,
                automation_enabled=False,
                final_response_checks=FAQFinalResponseChecks(
                    retrieved_evidence_present=True,
                    response_complete=True,
                    request_is_low_risk=True,
                    approved_faq_family_recognized=True,
                    request_topics_covered=True,
                    assessment_status_sufficient=True,
                    evidence_provenance_valid=True,
                    source_version_and_content_approved=True,
                    evidence_sections_match_request=True,
                    required_conditions_preserved=True,
                    no_prohibited_action_claims=True,
                    no_internal_identifiers=True,
                ),
                automation_eligibility=FAQAutomationEligibility(
                    eligible_candidate=True,
                    reason_codes=[],
                ),
                total_elapsed_seconds=1.4,
            ),
        )
        request = SupportDraftRequest(
            question="How do I download an issued invoice?"
        )
        repository = PostgresSupportRepository(
            dsn="postgresql://unused",
        )

        with patch("app.persistence.psycopg.connect", return_value=connection):
            repository.save_support_draft(
                draft_request=request,
                draft_response=draft,
            )

        self.assertTrue(connection.committed)
        self.assertIn("evidence_assessment", cursor.query)
        self.assertIn("generation_metadata", cursor.query)
        self.assertEqual(len(cursor.parameters), 19)
        self.assertEqual(cursor.parameters[17].obj, draft.evidence_assessment)
        self.assertEqual(
            cursor.parameters[18].obj,
            draft.generation_metadata.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )
        self.assertTrue(
            cursor.parameters[18].obj["automation_eligibility"]["eligible_candidate"]
        )


if __name__ == "__main__":
    unittest.main()
