import unittest
from datetime import date
from uuid import uuid4

from pydantic import ValidationError

from app.evidence_assessment import (
    EvidenceAssessmentProposal,
    EvidenceAssessmentValidationError,
    EvidenceQuote,
    RequestedInformationAssessment,
    SupportingFactAssessment,
    validate_and_aggregate_assessment,
)
from app.retrieval_repository import RetrievedChunk


def make_chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        source_id="synthetic-policy",
        title="Synthetic policy",
        policy_version="v1",
        effective_date=date(2026, 10, 6),
        access_scope="internal",
        chunk_index=0,
        section_path="Test section",
        text=text,
        cosine_distance=0.2,
    )


def make_requested_information(
    *,
    finding: str,
    evidence: list[EvidenceQuote] | None = None,
    answer: str | None = None,
    requested_information: str = "the requested fact",
) -> RequestedInformationAssessment:
    return RequestedInformationAssessment(
        requested_information=requested_information,
        finding=finding,
        answer=answer,
        evidence=evidence or [],
    )


class EvidenceAssessmentTests(unittest.TestCase):
    def test_supporting_fact_schema_only_allows_supported_finding(self):
        schema = EvidenceAssessmentProposal.model_json_schema()

        self.assertEqual(
            schema["$defs"]["SupportingFactAssessment"]["properties"]["finding"][
                "const"
            ],
            "supported",
        )

    def test_all_supported_claims_are_sufficient(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="supported",
                    requested_information="initial review duration",
                    answer="The initial review takes 2 business days.",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The initial review takes 2 business days.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "sufficient")
        self.assertEqual(decision.action, "draft_from_determined_claims")
        self.assertEqual(
            decision.requested_information[0].requested_information,
            "initial review duration",
        )
        self.assertEqual(
            decision.requested_information[0].answer,
            "The initial review takes 2 business days.",
        )

    def test_determined_requested_information_requires_an_answer(self):
        with self.assertRaisesRegex(ValidationError, "requires an answer"):
            make_requested_information(finding="supported")

    def test_undetermined_requested_information_must_not_have_an_answer(self):
        with self.assertRaisesRegex(ValidationError, "must not include an answer"):
            make_requested_information(
                finding="related_but_not_supported",
                answer="The reset link expires after 30 minutes.",
            )

    def test_requested_information_must_not_repeat_the_customer_question(self):
        with self.assertRaisesRegex(ValidationError, "not repeat the question"):
            RequestedInformationAssessment(
                requested_information="How long is the reset link valid?",
                finding="related_but_not_supported",
                answer=None,
                evidence=[],
            )

    def test_answer_must_be_declarative(self):
        with self.assertRaisesRegex(ValidationError, "must be declarative"):
            RequestedInformationAssessment(
                requested_information="initial review duration",
                finding="supported",
                answer="How long does the review take?",
                evidence=[],
            )

    def test_contradicted_claim_is_answerable_with_evidence(self):
        chunk = make_chunk("Support cannot bypass multi-factor authentication.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="contradicted",
                    requested_information="whether support can bypass MFA",
                    answer="Support cannot bypass multi-factor authentication.",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="Support cannot bypass multi-factor authentication.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "sufficient")

    def test_supported_context_fact_and_unsupported_request_are_partial(self):
        supported_chunk = make_chunk("The initial review takes 2 business days.")
        related_chunk = make_chunk(
            "The review window is not a guaranteed deadline for credit posting."
        )
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information="whether a credit will post within 2 business days",
                    finding="related_but_not_supported",
                    answer=None,
                    evidence=[
                        EvidenceQuote(
                            chunk_id=related_chunk.chunk_id,
                            quote=(
                                "The review window is not a guaranteed deadline "
                                "for credit posting."
                            ),
                        )
                    ],
                )
            ],
            supporting_facts=[
                SupportingFactAssessment(
                    claim="The initial review takes 2 business days.",
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=supported_chunk.chunk_id,
                            quote="The initial review takes 2 business days.",
                        )
                    ],
                )
            ],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[supported_chunk, related_chunk],
        )

        self.assertEqual(decision.status, "partial")
        self.assertEqual(
            decision.action,
            "draft_determined_claims_and_escalate",
        )
        self.assertEqual(len(decision.requested_information), 1)
        self.assertEqual(len(decision.supporting_facts), 1)

    def test_related_but_unsupported_claim_is_insufficient(self):
        chunk = make_chunk("The reset link is sent to the account email.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="related_but_not_supported",
                    requested_information="password-reset link expiry duration",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The reset link is sent to the account email.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "insufficient")
        self.assertEqual(decision.action, "state_missing_fact_and_escalate")
        self.assertEqual(
            decision.requested_information[0].requested_information,
            "password-reset link expiry duration",
        )
        self.assertIsNone(decision.requested_information[0].answer)

    def test_no_relevant_evidence_is_none_even_when_nearest_chunks_exist(self):
        nearest_chunk = make_chunk("A reported duplicate charge is reviewed.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="no_relevant_evidence",
                    requested_information="invoice download location",
                ),
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[nearest_chunk],
        )

        self.assertEqual(decision.status, "none")
        self.assertEqual(decision.action, "abstain_and_escalate")

    def test_no_relevant_evidence_can_be_returned_when_retrieval_is_empty(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="no_relevant_evidence",
                    requested_information="invoice download location",
                ),
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[],
        )

        self.assertEqual(decision.status, "none")

    def test_clarification_question_bypasses_claim_aggregation(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[],
            supporting_facts=[],
            clarifying_question="Are you unable to access your email or your account?",
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[],
        )

        self.assertEqual(decision.status, "clarification_needed")
        self.assertEqual(decision.action, "ask_clarifying_question")
        self.assertEqual(len(decision.requested_information), 0)
        self.assertEqual(len(decision.supporting_facts), 0)
        self.assertEqual(
            decision.clarifying_question,
            "Are you unable to access your email or your account?",
        )

    def test_conflicting_claim_blocks_draft_and_escalates(self):
        first_chunk = make_chunk("The review deadline is 2 business days.")
        second_chunk = make_chunk("The review deadline is 5 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="conflicting",
                    requested_information="duplicate-charge review deadline",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=first_chunk.chunk_id,
                            quote="The review deadline is 2 business days.",
                        ),
                        EvidenceQuote(
                            chunk_id=second_chunk.chunk_id,
                            quote="The review deadline is 5 business days.",
                        ),
                    ],
                )
            ],
            supporting_facts=[],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[first_chunk, second_chunk],
        )

        self.assertEqual(decision.status, "conflicting")
        self.assertEqual(decision.action, "abstain_and_escalate_conflict")

    def test_conflict_takes_precedence_over_other_claim_findings(self):
        first_chunk = make_chunk("The review deadline is 2 business days.")
        second_chunk = make_chunk("The review deadline is 5 business days.")
        supported_chunk = make_chunk("A confirmed duplicate charge is reversed.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="conflicting",
                    requested_information="duplicate-charge review deadline",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=first_chunk.chunk_id,
                            quote="The review deadline is 2 business days.",
                        ),
                        EvidenceQuote(
                            chunk_id=second_chunk.chunk_id,
                            quote="The review deadline is 5 business days.",
                        ),
                    ],
                ),
            ],
            supporting_facts=[
                SupportingFactAssessment(
                    claim="A confirmed duplicate charge is reversed.",
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=supported_chunk.chunk_id,
                            quote="A confirmed duplicate charge is reversed.",
                        )
                    ],
                )
            ],
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[first_chunk, second_chunk, supported_chunk],
        )

        self.assertEqual(decision.status, "conflicting")
        self.assertEqual(decision.action, "abstain_and_escalate_conflict")

    def test_supported_finding_requires_evidence(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="supported",
                    answer="The requested information is established.",
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "requires at least one evidence quote",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_related_but_unsupported_finding_requires_context_evidence(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="related_but_not_supported",
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "requires at least one evidence quote",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_evidence_must_reference_a_retrieved_chunk(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="supported",
                    answer="The requested information is established.",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=uuid4(),
                            quote="The requested fact is supported.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "was not retrieved",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_quote_must_be_an_exact_substring_of_its_chunk(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="supported",
                    answer="The initial review takes 2 business days.",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The initial review takes 3 business days.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "not an exact substring",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_no_relevant_evidence_must_not_reference_a_chunk(self):
        chunk = make_chunk("The retrieved text is not relevant to the question.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="no_relevant_evidence",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The retrieved text is not relevant to the question.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "must not cite chunks",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_conflicting_finding_requires_quotes_from_distinct_chunks(self):
        chunk = make_chunk("The review deadline is 2 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                make_requested_information(
                    finding="conflicting",
                    requested_information="duplicate-charge review deadline",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The review deadline is 2 business days.",
                        ),
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The review deadline is 2 business days.",
                        ),
                    ],
                )
            ],
            supporting_facts=[],
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "at least two distinct retrieved chunks",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_assessment_must_be_claims_or_one_clarifying_question(self):
        with self.assertRaises(ValidationError):
            EvidenceAssessmentProposal(
                requested_information=[],
                supporting_facts=[],
            )

        with self.assertRaises(ValidationError):
            EvidenceAssessmentProposal(
                requested_information=[
                    make_requested_information(
                        finding="no_relevant_evidence",
                    )
                ],
                supporting_facts=[],
                clarifying_question="Which account issue are you experiencing?",
            )


if __name__ == "__main__":
    unittest.main()
