import json
import unittest
from datetime import date
from uuid import uuid4

from app.evidence_assessment import (
    EvidenceAssessmentProposal,
    EvidenceQuote,
    RequestedInformationAssessment,
    SupportingFactAssessment,
)
from app.evidence_assessor import EvidenceAssessorError, OllamaEvidenceAssessor
from app.llm_provider import OllamaProviderError
from app.retrieval_repository import RetrievedChunk


class FakeStructuredOutputGenerator:
    def __init__(
        self,
        *,
        response: str | None = None,
        error: OllamaProviderError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate_structured(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        self.calls.append(
            {
                "model_name": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_schema": response_schema,
            }
        )
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("A fake response or provider error is required.")
        return self.response


def make_chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        source_id="synthetic-billing-policy",
        title="Duplicate charge policy",
        policy_version="v1",
        effective_date=date(2026, 10, 6),
        access_scope="internal",
        chunk_index=0,
        section_path="Duplicate charges",
        text=text,
        cosine_distance=0.2,
    )


class OllamaEvidenceAssessorTests(unittest.TestCase):
    def test_assess_separates_requested_claim_from_supported_context(self):
        review_chunk = make_chunk(
            "Reported duplicate charges are reviewed within 2 business days."
        )
        credit_chunk = make_chunk(
            "The initial review window is not a guaranteed deadline for final "
            "resolution or for a credit to appear in a payment account."
        )
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information=(
                        "whether the credit will appear within 2 business days"
                    ),
                    finding="related_but_not_supported",
                    answer=None,
                    evidence=[
                        EvidenceQuote(
                            chunk_id=credit_chunk.chunk_id,
                            quote=(
                                "The initial review window is not a guaranteed "
                                "deadline for final resolution or for a credit "
                                "to appear in a payment account."
                            ),
                        )
                    ],
                ),
            ],
            supporting_facts=[
                SupportingFactAssessment(
                    claim=(
                        "Reported duplicate charges are reviewed within "
                        "2 business days."
                    ),
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=review_chunk.chunk_id,
                            quote=(
                                "Reported duplicate charges are reviewed within "
                                "2 business days."
                            ),
                        )
                    ],
                ),
                SupportingFactAssessment(
                    claim=(
                        "The review window does not guarantee a credit-posting "
                        "date."
                    ),
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=credit_chunk.chunk_id,
                            quote=(
                                "The initial review window is not a guaranteed "
                                "deadline for final resolution or for a credit "
                                "to appear in a payment account."
                            ),
                        )
                    ],
                ),
            ]
        )
        generator = FakeStructuredOutputGenerator(response=proposal.model_dump_json())
        assessor = OllamaEvidenceAssessor(
            generator=generator,
            model_name="qwen3:4b",
        )

        decision = assessor.assess(
            question=(
                "I was charged twice. Will the credit appear within 2 business days?"
            ),
            retrieved_chunks=[review_chunk, credit_chunk],
        )

        self.assertEqual(decision.status, "partial")
        self.assertEqual(decision.action, "draft_determined_claims_and_escalate")
        self.assertEqual(len(decision.requested_information), 1)
        self.assertIsNone(decision.requested_information[0].answer)
        self.assertEqual(len(decision.supporting_facts), 2)
        self.assertEqual(generator.calls[0]["model_name"], "qwen3:4b")
        self.assertEqual(
            generator.calls[0]["response_schema"],
            EvidenceAssessmentProposal.model_json_schema(),
        )
        user_prompt = generator.calls[0]["user_prompt"]
        self.assertIn("I was charged twice", user_prompt)
        self.assertIn(str(review_chunk.chunk_id), user_prompt)
        self.assertNotIn("cosine_distance", user_prompt)

    def test_assess_returns_clarification_decision(self):
        proposal = EvidenceAssessmentProposal(
            requested_information=[],
            supporting_facts=[],
            clarifying_question="Is this a duplicate charge or another billing issue?",
        )
        assessor = OllamaEvidenceAssessor(
            generator=FakeStructuredOutputGenerator(
                response=proposal.model_dump_json()
            ),
            model_name="qwen3:4b",
        )

        decision = assessor.assess(
            question="Something is wrong with my bill. Can you refund it?",
            retrieved_chunks=[],
        )

        self.assertEqual(decision.status, "clarification_needed")
        self.assertEqual(decision.action, "ask_clarifying_question")

    def test_assess_returns_none_when_model_finds_no_relevant_evidence(self):
        chunk = make_chunk("A duplicate charge is reviewed within 2 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information="invoice download location",
                    finding="no_relevant_evidence",
                    answer=None,
                    evidence=[],
                )
            ],
            supporting_facts=[],
        )
        assessor = OllamaEvidenceAssessor(
            generator=FakeStructuredOutputGenerator(
                response=proposal.model_dump_json()
            ),
            model_name="qwen3:4b",
        )

        decision = assessor.assess(
            question="Where can I download my invoice?",
            retrieved_chunks=[chunk],
        )

        self.assertEqual(decision.status, "none")
        self.assertEqual(decision.action, "abstain_and_escalate")

    def test_invalid_model_output_fails_closed(self):
        for raw_output in (
            "not JSON",
            '{"requested_information": [], "supporting_facts": []}',
        ):
            with self.subTest(raw_output=raw_output):
                assessor = OllamaEvidenceAssessor(
                    generator=FakeStructuredOutputGenerator(response=raw_output),
                    model_name="qwen3:4b",
                )

                with self.assertRaisesRegex(
                    EvidenceAssessorError,
                    "invalid evidence assessment proposal",
                ):
                    assessor.assess(
                        question="How long does review take?",
                        retrieved_chunks=[],
                    )

    def test_schema_validation_error_identifies_the_invalid_field(self):
        raw_output = json.dumps(
            {
                "requested_information": [
                    {
                        "requested_information": "initial review duration",
                        "finding": "supported",
                        "answer": None,
                        "evidence": [],
                    }
                ],
                "supporting_facts": [],
            }
        )
        assessor = OllamaEvidenceAssessor(
            generator=FakeStructuredOutputGenerator(response=raw_output),
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(
            EvidenceAssessorError,
            r"requested_information\.0.*requires an answer",
        ):
            assessor.assess(
                question="How long does the initial review take?",
                retrieved_chunks=[],
            )

    def test_duplicate_requested_answer_and_supporting_fact_fails_closed(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        shared_fact = {
            "claim": "The initial review takes 2 business days.",
            "finding": "supported",
            "evidence": [
                {
                    "chunk_id": str(chunk.chunk_id),
                    "quote": "The initial review takes 2 business days.",
                }
            ],
        }
        generator = FakeStructuredOutputGenerator(
            response=json.dumps(
                {
                    "requested_information": [
                        {
                            "requested_information": "initial review duration",
                            "finding": "supported",
                            "answer": "The initial review takes 2 business days.",
                            "evidence": shared_fact["evidence"],
                        }
                    ],
                    "supporting_facts": [shared_fact],
                }
            )
        )
        assessor = OllamaEvidenceAssessor(
            generator=generator,
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(
            EvidenceAssessorError,
            "invalid evidence assessment proposal",
        ):
            assessor.assess(
                question="How long does the initial review take?",
                retrieved_chunks=[chunk],
            )

    def test_unsupported_supporting_fact_fails_closed(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        generator = FakeStructuredOutputGenerator(
            response=json.dumps(
                {
                    "requested_information": [
                        {
                            "requested_information": (
                                "whether a credit will post within 2 business days"
                            ),
                            "finding": "related_but_not_supported",
                            "answer": None,
                            "evidence": [
                                {
                                    "chunk_id": str(chunk.chunk_id),
                                    "quote": (
                                        "The initial review takes 2 business days."
                                    ),
                                }
                            ],
                        }
                    ],
                    "supporting_facts": [
                        {
                            "claim": "The initial review takes 2 business days.",
                            "finding": "related_but_not_supported",
                            "evidence": [
                                {
                                    "chunk_id": str(chunk.chunk_id),
                                    "quote": (
                                        "The initial review takes 2 business days."
                                    ),
                                }
                            ],
                        }
                    ],
                }
            )
        )
        assessor = OllamaEvidenceAssessor(
            generator=generator,
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(
            EvidenceAssessorError,
            "invalid evidence assessment proposal",
        ):
            assessor.assess(
                question="Will the credit post within 2 business days?",
                retrieved_chunks=[chunk],
            )

    def test_non_verbatim_model_quote_fails_closed(self):
        chunk = make_chunk("The initial review takes 2 business days.")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information="initial review duration",
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
        assessor = OllamaEvidenceAssessor(
            generator=FakeStructuredOutputGenerator(
                response=proposal.model_dump_json()
            ),
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(
            EvidenceAssessorError,
            "retrieved-chunk and quote validation",
        ):
            assessor.assess(
                question="How long does the initial review take?",
                retrieved_chunks=[chunk],
            )

    def test_provider_failure_fails_closed(self):
        assessor = OllamaEvidenceAssessor(
            generator=FakeStructuredOutputGenerator(
                error=OllamaProviderError("Ollama connection error: unavailable")
            ),
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(
            EvidenceAssessorError,
            "generation failed",
        ):
            assessor.assess(
                question="How long does the initial review take?",
                retrieved_chunks=[],
            )

    def test_blank_question_is_rejected_before_provider_call(self):
        generator = FakeStructuredOutputGenerator(response="{}")
        assessor = OllamaEvidenceAssessor(
            generator=generator,
            model_name="qwen3:4b",
        )

        with self.assertRaisesRegex(ValueError, "question must not be blank"):
            assessor.assess(question=" \n", retrieved_chunks=[])

        self.assertEqual(generator.calls, [])


if __name__ == "__main__":
    unittest.main()
