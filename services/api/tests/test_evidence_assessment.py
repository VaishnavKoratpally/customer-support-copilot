import unittest
from datetime import date
from uuid import uuid4

from pydantic import ValidationError

from app.evidence_assessment import (
    ClaimAssessment,
    EvidenceAssessmentProposal,
    EvidenceAssessmentValidationError,
    EvidenceQuote,
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


def make_claim(
    *,
    finding: str,
    evidence: list[EvidenceQuote] | None = None,
) -> ClaimAssessment:
    return ClaimAssessment(
        claim="The requested fact",
        finding=finding,
        evidence=evidence or [],
    )


class EvidenceAssessmentTests(unittest.TestCase):
    def test_all_supported_claims_are_sufficient(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The initial review takes 2 business days.",
                        )
                    ],
                )
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "sufficient")
        self.assertEqual(decision.action, "draft_from_determined_claims")

    def test_contradicted_claim_is_answerable_with_evidence(self):
        chunk = make_chunk("Support cannot bypass multi-factor authentication.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="contradicted",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="Support cannot bypass multi-factor authentication.",
                        )
                    ],
                )
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "sufficient")

    def test_supported_and_related_but_unsupported_claims_are_partial(self):
        supported_chunk = make_chunk("The initial review takes 2 business days.")
        related_chunk = make_chunk(
            "The review window is not a guaranteed deadline for credit posting."
        )
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=supported_chunk.chunk_id,
                            quote="The initial review takes 2 business days.",
                        )
                    ],
                ),
                ClaimAssessment(
                    claim="The credit will post within 2 business days.",
                    finding="related_but_not_supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=related_chunk.chunk_id,
                            quote=(
                                "The review window is not a guaranteed deadline "
                                "for credit posting."
                            ),
                        )
                    ],
                ),
            ]
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

    def test_related_but_unsupported_claim_is_insufficient(self):
        chunk = make_chunk("The reset link is sent to the account email.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="related_but_not_supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The reset link is sent to the account email.",
                        )
                    ],
                )
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "insufficient")
        self.assertEqual(decision.action, "state_missing_fact_and_escalate")

    def test_no_relevant_evidence_is_none_even_when_nearest_chunks_exist(self):
        nearest_chunk = make_chunk("A reported duplicate charge is reviewed.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(finding="no_relevant_evidence"),
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[nearest_chunk],
        )

        self.assertEqual(decision.status, "none")
        self.assertEqual(decision.action, "abstain_and_escalate")

    def test_no_relevant_evidence_can_be_returned_when_retrieval_is_empty(self):
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(finding="no_relevant_evidence"),
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[],
        )

        self.assertEqual(decision.status, "none")

    def test_clarification_question_bypasses_claim_aggregation(self):
        proposal = EvidenceAssessmentProposal(
            claims=[],
            clarifying_question="Are you unable to access your email or your account?",
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[],
        )

        self.assertEqual(decision.status, "clarification_needed")
        self.assertEqual(decision.action, "ask_clarifying_question")
        self.assertEqual(len(decision.claims), 0)
        self.assertEqual(
            decision.clarifying_question,
            "Are you unable to access your email or your account?",
        )

    def test_conflicting_claim_blocks_draft_and_escalates(self):
        first_chunk = make_chunk("The review deadline is 2 business days.")
        second_chunk = make_chunk("The review deadline is 5 business days.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="conflicting",
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
            ]
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
            claims=[
                make_claim(
                    finding="conflicting",
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
                make_claim(
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=supported_chunk.chunk_id,
                            quote="A confirmed duplicate charge is reversed.",
                        )
                    ],
                ),
            ]
        )

        decision = validate_and_aggregate_assessment(
            proposal,
            retrieved_chunks=[first_chunk, second_chunk, supported_chunk],
        )

        self.assertEqual(decision.status, "conflicting")
        self.assertEqual(decision.action, "abstain_and_escalate_conflict")

    def test_supported_finding_requires_evidence(self):
        proposal = EvidenceAssessmentProposal(
            claims=[make_claim(finding="supported")]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "requires at least one evidence quote",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_related_but_unsupported_finding_requires_context_evidence(self):
        proposal = EvidenceAssessmentProposal(
            claims=[make_claim(finding="related_but_not_supported")]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "requires at least one evidence quote",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_evidence_must_reference_a_retrieved_chunk(self):
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=uuid4(),
                            quote="The requested fact is supported.",
                        )
                    ],
                )
            ]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "was not retrieved",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[])

    def test_quote_must_be_an_exact_substring_of_its_chunk(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The initial review takes 3 business days.",
                        )
                    ],
                )
            ]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "not an exact substring",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_no_relevant_evidence_must_not_reference_a_chunk(self):
        chunk = make_chunk("The retrieved text is not relevant to the question.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="no_relevant_evidence",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote="The retrieved text is not relevant to the question.",
                        )
                    ],
                )
            ]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "must not cite chunks",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_conflicting_finding_requires_quotes_from_distinct_chunks(self):
        chunk = make_chunk("The review deadline is 2 business days.")
        proposal = EvidenceAssessmentProposal(
            claims=[
                make_claim(
                    finding="conflicting",
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
            ]
        )

        with self.assertRaisesRegex(
            EvidenceAssessmentValidationError,
            "at least two distinct retrieved chunks",
        ):
            validate_and_aggregate_assessment(proposal, retrieved_chunks=[chunk])

    def test_assessment_must_be_claims_or_one_clarifying_question(self):
        with self.assertRaises(ValidationError):
            EvidenceAssessmentProposal(claims=[])

        with self.assertRaises(ValidationError):
            EvidenceAssessmentProposal(
                claims=[make_claim(finding="no_relevant_evidence")],
                clarifying_question="Which account issue are you experiencing?",
            )


if __name__ == "__main__":
    unittest.main()
