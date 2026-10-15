import json
import unittest
from datetime import date
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.config import Settings
from app.faq_automation import APPROVED_FAQ_CONTENT_SHA256
from app.evidence_assessment import (
    EvidenceAssessmentProposal,
    EvidenceQuote,
    RequestedInformationAssessment,
    SupportingFactAssessment,
)
from app.llm_provider import (
    OllamaGenerationMetrics,
    OllamaGenerationResult,
    OllamaProviderError,
)
from app.orchestrator import (
    DraftGenerationError,
    GeneratedDraftOrchestrator,
    PreviewOnlyDraftOrchestrator,
)
from app.retrieval_repository import RetrievedChunk
from app.retriever import VectorRetrievalResult
from app.schemas import (
    DraftModelCallMetrics,
    SupportDraftGenerationMetadata,
    SupportDraftRequest,
    SupportDraftResponse,
)


ROLE_QUOTE = (
    "Only workspace owners and billing admins can download issued invoices "
    "for a workspace they are authorized to access."
)
STEPS_QUOTE = (
    "To download an issued invoice, sign in, open Billing > Invoices, select "
    "the invoice, and choose Download PDF."
)


def make_generation_metrics(
    *,
    eval_count: int = 120,
    done_reason: str | None = "stop",
    done: bool | None = True,
) -> OllamaGenerationMetrics:
    return OllamaGenerationMetrics(
        total_duration_ns=1_000_000_000,
        load_duration_ns=100_000_000,
        prompt_eval_count=200,
        prompt_eval_duration_ns=100_000_000,
        eval_count=eval_count,
        eval_duration_ns=700_000_000,
        done_reason=done_reason,
        done=done,
    )


def make_chunk(
    text: str,
    *,
    source_id: str = "billing-invoice-faq-01",
    section_path: str = "Invoice copies",
    policy_version: str = "week4-synthetic-v1",
    access_scope: str = "public",
    source_checksum_sha256: str | None = None,
) -> RetrievedChunk:
    if source_checksum_sha256 is None and source_id == "billing-invoice-faq-01":
        source_checksum_sha256 = APPROVED_FAQ_CONTENT_SHA256
    return RetrievedChunk(
        chunk_id=uuid4(),
        source_id=source_id,
        title="Synthetic Invoice Copies and Fields FAQ",
        policy_version=policy_version,
        effective_date=date(2026, 10, 14),
        access_scope=access_scope,
        chunk_index=0,
        section_path=section_path,
        text=text,
        cosine_distance=0.12,
        source_checksum_sha256=source_checksum_sha256,
    )


def supported_invoice_proposal(chunk: RetrievedChunk) -> EvidenceAssessmentProposal:
    return EvidenceAssessmentProposal(
        requested_information=[
            RequestedInformationAssessment(
                requested_information="how to download an issued invoice pdf",
                finding="supported",
                answer=(
                    "Workspace owners and billing admins authorized for the "
                    "workspace can download an issued invoice PDF from Billing "
                    "> Invoices by selecting the invoice and choosing Download PDF."
                ),
                evidence=[
                    EvidenceQuote(chunk_id=chunk.chunk_id, quote=ROLE_QUOTE),
                    EvidenceQuote(chunk_id=chunk.chunk_id, quote=STEPS_QUOTE),
                ],
            )
        ],
        supporting_facts=[],
    )


class FakeRetriever:
    def __init__(self, hits: tuple[RetrievedChunk, ...]) -> None:
        self.hits = hits
        self.received_question: str | None = None
        self.received_top_k: int | None = None

    def retrieve(self, question: str, *, top_k: int = 3) -> VectorRetrievalResult:
        self.received_question = question
        self.received_top_k = top_k
        return VectorRetrievalResult(hits=self.hits)


class FakeGenerationProvider:
    def __init__(
        self,
        *,
        assessment: EvidenceAssessmentProposal | str | None = None,
        assessment_call_metrics: OllamaGenerationMetrics | None = None,
        draft_text: str = (
            "Only workspace owners and billing admins authorized to access the "
            "workspace can download an issued invoice as a PDF. Sign in, open Billing > "
            "Invoices, select the invoice, and choose Download PDF."
        ),
        generation_output: str | None = None,
        generation_call_metrics: OllamaGenerationMetrics | None = None,
        assessment_error: Exception | None = None,
        generation_error: Exception | None = None,
    ) -> None:
        self.assessment = assessment
        self.assessment_metrics = (
            assessment_call_metrics or make_generation_metrics()
        )
        self.draft_text = draft_text
        self.generation_output = generation_output
        self.generation_metrics = generation_call_metrics or make_generation_metrics(
            eval_count=45,
        )
        self.assessment_error = assessment_error
        self.generation_error = generation_error
        self.structured_calls: list[dict[str, object]] = []
        self.assessment_calls: list[dict[str, object]] = []
        self.generation_calls: list[dict[str, object]] = []

    def generate_structured_with_metrics(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
        max_output_tokens: int = 1024,
    ) -> OllamaGenerationResult:
        call = {
            "model_name": model_name,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_schema": response_schema,
            "max_output_tokens": max_output_tokens,
        }
        self.structured_calls.append(call)
        properties = response_schema.get("properties")
        if isinstance(properties, dict) and "draft" in properties:
            self.generation_calls.append(call)
            if self.generation_error is not None:
                raise self.generation_error
            return OllamaGenerationResult(
                text=(
                    self.generation_output
                    if self.generation_output is not None
                    else json.dumps({"draft": self.draft_text})
                ),
                metrics=self.generation_metrics,
            )

        self.assessment_calls.append(call)
        if self.assessment_error is not None:
            raise self.assessment_error
        if self.assessment is None:
            raise AssertionError("A structured assessment or provider error is required.")
        text = (
            self.assessment.model_dump_json()
            if isinstance(self.assessment, EvidenceAssessmentProposal)
            else self.assessment
        )
        return OllamaGenerationResult(text=text, metrics=self.assessment_metrics)


class GeneratedSupportDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.question = "How do I download a PDF copy of an issued invoice?"
        self.payload = SupportDraftRequest(question=self.question)
        self.chunk = make_chunk(f"{ROLE_QUOTE}\n\n{STEPS_QUOTE}")

    def make_orchestrator(
        self,
        provider: FakeGenerationProvider,
        hits: tuple[RetrievedChunk, ...] | None = None,
        *,
        automation_enabled: bool = False,
    ) -> tuple[GeneratedDraftOrchestrator, FakeRetriever]:
        retriever = FakeRetriever((self.chunk,) if hits is None else hits)
        return (
            GeneratedDraftOrchestrator(
                retriever=retriever,
                provider=provider,
                assessor_model="qwen3:4b",
                generator_model="qwen3:4b",
                max_output_tokens=256,
                automation_enabled=automation_enabled,
            ),
            retriever,
        )

    def test_supported_faq_is_assessed_then_generated_and_stays_review_first(self):
        irrelevant = make_chunk(
            "A workspace subscription can be changed by an authorized owner.",
            source_id="account-plan-01",
        )
        provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
        )
        orchestrator, retriever = self.make_orchestrator(
            provider,
            hits=(self.chunk, irrelevant),
        )

        response = orchestrator.draft_reply(self.payload)

        self.assertEqual(retriever.received_question, self.question)
        self.assertEqual(retriever.received_top_k, 3)
        self.assertEqual(len(provider.structured_calls), 2)
        self.assertEqual(len(provider.assessment_calls), 1)
        self.assertEqual(len(provider.generation_calls), 1)
        self.assertEqual(provider.structured_calls[0]["model_name"], "qwen3:4b")
        self.assertEqual(provider.generation_calls[0]["model_name"], "qwen3:4b")
        self.assertEqual(provider.generation_calls[0]["max_output_tokens"], 256)
        self.assertEqual(
            provider.generation_calls[0]["response_schema"]["required"],
            ["draft"],
        )
        self.assertFalse(
            provider.generation_calls[0]["response_schema"]["additionalProperties"]
        )
        self.assertIn(
            "one to three short sentences",
            provider.generation_calls[0]["system_prompt"],
        )
        self.assertIn(
            "Do not explain the task",
            provider.generation_calls[0]["system_prompt"],
        )
        self.assertIn(ROLE_QUOTE, provider.generation_calls[0]["user_prompt"])
        self.assertNotIn(
            irrelevant.text,
            provider.generation_calls[0]["user_prompt"],
        )
        self.assertEqual(response.draft_mode, "generated")
        self.assertEqual(response.draft, provider.draft_text)
        self.assertEqual([item.chunk_id for item in response.citations], [self.chunk.chunk_id])
        self.assertEqual(response.citation_source_ids, ["billing-invoice-faq-01"])
        self.assertTrue(response.citation_contract_passed)
        self.assertEqual(response.evidence_assessment["status"], "sufficient")
        self.assertTrue(response.requires_human_review)
        self.assertEqual(response.review_status, "pending_review")
        self.assertIsNone(response.retrieval_confidence)
        self.assertIsNone(response.answer_confidence)
        self.assertEqual(response.review_triggers, ["generated_pilot_review_first"])
        self.assertEqual(response.generation_metadata.outcome, "generated")
        self.assertTrue(response.generation_metadata.generation_completion_verified)
        self.assertFalse(response.generation_metadata.automation_enabled)
        self.assertTrue(
            response.generation_metadata.automation_eligibility.eligible_candidate
        )
        self.assertEqual(
            response.generation_metadata.automation_eligibility.semantic_review_status,
            "not_performed",
        )
        self.assertTrue(
            all(
                response.generation_metadata.final_response_checks.model_dump().values()
            )
        )
        self.assertEqual(response.generation_metadata.assessor_model, "qwen3:4b")
        self.assertEqual(response.generation_metadata.generator_model, "qwen3:4b")
        self.assertEqual(response.generation_metadata.generator_max_output_tokens, 256)
        self.assertEqual(
            len(response.generation_metadata.assessor_user_prompt_sha256),
            64,
        )
        self.assertEqual(
            len(response.generation_metadata.generator_user_prompt_sha256),
            64,
        )
        self.assertEqual(
            len(response.generation_metadata.generator_schema_sha256),
            64,
        )

    def test_automation_enablement_only_handles_a_fully_eligible_candidate(self):
        enabled_provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
        )
        enabled_orchestrator, _ = self.make_orchestrator(
            enabled_provider,
            automation_enabled=True,
        )

        eligible = enabled_orchestrator.draft_reply(self.payload)

        self.assertTrue(eligible.generation_metadata.automation_enabled)
        self.assertTrue(
            eligible.generation_metadata.automation_eligibility.eligible_candidate
        )
        self.assertFalse(eligible.requires_human_review)
        self.assertEqual(eligible.review_status, "not_required")
        self.assertEqual(eligible.review_triggers, [])
        self.assertIsNone(eligible.escalation_reason)
        self.assertIsNone(eligible.retrieval_confidence)
        self.assertIsNone(eligible.answer_confidence)

        generic_provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
        )
        generic_orchestrator, _ = self.make_orchestrator(
            generic_provider,
            automation_enabled=True,
        )
        generic = generic_orchestrator.draft_reply(
            SupportDraftRequest(question="I need help with my invoice.")
        )

        self.assertEqual(generic.risk_level, "low")
        self.assertTrue(generic.requires_human_review)
        self.assertEqual(generic.review_status, "pending_review")
        self.assertFalse(
            generic.generation_metadata.automation_eligibility.eligible_candidate
        )
        self.assertIn(
            "request_family_not_approved",
            generic.generation_metadata.automation_eligibility.reason_codes,
        )

    def test_approved_invoice_field_faqs_can_be_eligible(self):
        cases = (
            (
                "What does the invoice number identify?",
                "invoice number meaning",
                "An invoice number identifies the invoice document; it is not an account number or proof that payment has been completed.",
                "An invoice number identifies the invoice document; it is not an account number or proof that payment has been completed.",
            ),
            (
                "What does the billing period on an invoice cover?",
                "billing period coverage",
                "The billing period is the date range covered by the invoice's charges; it is not the payment-due date.",
                "The billing period is the date range covered by the invoice's charges; it is not the payment-due date.",
            ),
            (
                "What does the currency field mean?",
                "currency denomination",
                "The currency field identifies the denomination of invoice amounts; it does not provide an exchange rate.",
                "The currency field identifies the denomination of invoice amounts; it does not provide an exchange rate.",
            ),
        )
        for question, label, quote, draft in cases:
            with self.subTest(question=question):
                chunk = make_chunk(quote, section_path="Invoice fields")
                assessment = EvidenceAssessmentProposal(
                    requested_information=[
                        RequestedInformationAssessment(
                            requested_information=label,
                            finding="supported",
                            answer=quote,
                            evidence=[EvidenceQuote(chunk_id=chunk.chunk_id, quote=quote)],
                        )
                    ],
                    supporting_facts=[],
                )
                provider = FakeGenerationProvider(
                    assessment=assessment,
                    draft_text=draft,
                )
                orchestrator, _ = self.make_orchestrator(
                    provider,
                    hits=(chunk,),
                    automation_enabled=True,
                )

                response = orchestrator.draft_reply(
                    SupportDraftRequest(question=question)
                )

                self.assertTrue(
                    response.generation_metadata.automation_eligibility.eligible_candidate
                )
                self.assertFalse(response.requires_human_review)
                self.assertEqual(response.review_status, "not_required")

    def test_final_checks_block_out_of_scope_unapproved_or_unsafe_candidates(self):
        unapproved_checksum = make_chunk(
            f"{ROLE_QUOTE}\n\n{STEPS_QUOTE}",
            source_checksum_sha256="b" * 64,
        )
        wrong_section = make_chunk(
            f"{ROLE_QUOTE}\n\n{STEPS_QUOTE}",
            section_path="Invoice fields",
        )
        cases = (
            (
                "out_of_scope_email",
                SupportDraftRequest(
                    question="Can you email me a PDF copy of an issued invoice?"
                ),
                self.chunk,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(self.chunk)
                ),
                "out_of_scope_request",
            ),
            (
                "unapproved_source_content",
                self.payload,
                unapproved_checksum,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(unapproved_checksum)
                ),
                "source_version_or_content_not_approved",
            ),
            (
                "evidence_section_mismatch",
                self.payload,
                wrong_section,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(wrong_section)
                ),
                "evidence_section_mismatch",
            ),
            (
                "missing_access_condition",
                self.payload,
                self.chunk,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(self.chunk),
                    draft_text=(
                        "Workspace owners and billing admins can download an "
                        "issued invoice PDF. Sign in, open Billing > Invoices, "
                        "select the invoice, and choose Download PDF."
                    ),
                ),
                "required_condition_missing",
            ),
            (
                "prohibited_action_claim",
                self.payload,
                self.chunk,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(self.chunk),
                    draft_text=(
                        "We are emailing an invoice now. Only workspace owners "
                        "and billing admins authorized to access the workspace "
                        "can download an issued invoice as a PDF."
                    ),
                ),
                "prohibited_action_claim",
            ),
            (
                "internal_identifier",
                self.payload,
                self.chunk,
                FakeGenerationProvider(
                    assessment=supported_invoice_proposal(self.chunk),
                    draft_text=(
                        "Only workspace owners and billing admins authorized "
                        "to access the workspace can download an issued invoice "
                        "as a PDF. Source ID: billing-invoice-faq-01."
                    ),
                ),
                "internal_identifier_in_response",
            ),
        )
        for case_name, request, chunk, provider, reason in cases:
            with self.subTest(case=case_name):
                orchestrator, _ = self.make_orchestrator(
                    provider,
                    hits=(chunk,),
                    automation_enabled=True,
                )

                response = orchestrator.draft_reply(request)

                self.assertTrue(response.requires_human_review)
                self.assertEqual(response.review_status, "pending_review")
                self.assertIn(
                    reason,
                    response.generation_metadata.automation_eligibility.reason_codes,
                )

    def test_partial_assessment_generates_only_with_explicit_missing_part(self):
        unsupported_quote = "This FAQ does not specify when a credit will post."
        review_quote = "Reported duplicate charges are reviewed within 2 business days."
        chunk = make_chunk(f"{unsupported_quote} {review_quote}")
        proposal = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information="credit posting date",
                    finding="related_but_not_supported",
                    answer=None,
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote=unsupported_quote,
                        )
                    ],
                )
            ],
            supporting_facts=[
                SupportingFactAssessment(
                    claim="Reported duplicate charges are reviewed within 2 business days.",
                    finding="supported",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=chunk.chunk_id,
                            quote=review_quote,
                        )
                    ],
                )
            ],
        )
        provider = FakeGenerationProvider(assessment=proposal)
        orchestrator, _ = self.make_orchestrator(provider, hits=(chunk,))

        response = orchestrator.draft_reply(
            SupportDraftRequest(
                question=(
                    "I was charged twice. When will the credit post, and how "
                    "long is the initial review?"
                )
            )
        )

        self.assertEqual(response.evidence_assessment["status"], "partial")
        self.assertEqual(len(provider.generation_calls), 1)
        self.assertIn(
            "credit posting date",
            provider.generation_calls[0]["user_prompt"],
        )
        self.assertIn('"answer": null', provider.generation_calls[0]["user_prompt"])
        self.assertIn("evidence_status_partial", response.review_triggers)
        self.assertEqual(response.review_status, "pending_review")

    def test_no_retrieval_returns_explicit_abstention_without_model_calls(self):
        provider = FakeGenerationProvider()
        orchestrator, _ = self.make_orchestrator(
            provider,
            hits=(),
            automation_enabled=True,
        )

        response = orchestrator.draft_reply(self.payload)

        self.assertEqual(response.generation_metadata.outcome, "no_retrieved_evidence")
        self.assertIn("No verified support guidance was retrieved", response.draft)
        self.assertEqual(response.citations, [])
        self.assertFalse(response.citation_contract_passed)
        self.assertEqual(provider.structured_calls, [])
        self.assertEqual(provider.generation_calls, [])
        self.assertTrue(response.requires_human_review)
        self.assertEqual(response.review_status, "pending_review")
        self.assertIsNone(response.evidence_assessment)
        self.assertIsNone(response.generation_metadata.assessor_model)
        self.assertFalse(
            response.generation_metadata.automation_eligibility.eligible_candidate
        )
        self.assertTrue(response.generation_metadata.automation_enabled)
        self.assertIn(
            "no_retrieved_evidence",
            response.generation_metadata.automation_eligibility.reason_codes,
        )

    def test_none_insufficient_and_clarification_do_not_generate_customer_text(self):
        cases = (
            (
                EvidenceAssessmentProposal(
                    requested_information=[
                        RequestedInformationAssessment(
                            requested_information="invoice download instructions",
                            finding="no_relevant_evidence",
                            answer=None,
                            evidence=[],
                        )
                    ],
                    supporting_facts=[],
                ),
                "no_relevant_evidence",
            ),
            (
                EvidenceAssessmentProposal(
                    requested_information=[
                        RequestedInformationAssessment(
                            requested_information="invoice due date",
                            finding="related_but_not_supported",
                            answer=None,
                            evidence=[
                                EvidenceQuote(
                                    chunk_id=self.chunk.chunk_id,
                                    quote=ROLE_QUOTE,
                                )
                            ],
                        )
                    ],
                    supporting_facts=[],
                ),
                "insufficient_evidence",
            ),
            (
                EvidenceAssessmentProposal(
                    requested_information=[],
                    supporting_facts=[],
                    clarifying_question="Are you asking for a copy or a charge review?",
                ),
                "clarification_needed",
            ),
        )
        for proposal, expected_outcome in cases:
            with self.subTest(outcome=expected_outcome):
                provider = FakeGenerationProvider(assessment=proposal)
                orchestrator, _ = self.make_orchestrator(provider)

                response = orchestrator.draft_reply(self.payload)

                self.assertEqual(response.generation_metadata.outcome, expected_outcome)
                self.assertEqual(len(provider.structured_calls), 1)
                self.assertEqual(provider.generation_calls, [])
                self.assertTrue(response.requires_human_review)
                self.assertEqual(response.review_status, "pending_review")
                self.assertIsNone(response.answer_confidence)

    def test_high_risk_sufficient_draft_still_requires_human_review(self):
        proposal = supported_invoice_proposal(self.chunk)
        provider = FakeGenerationProvider(assessment=proposal)
        orchestrator, _ = self.make_orchestrator(
            provider,
            automation_enabled=True,
        )

        response = orchestrator.draft_reply(
            SupportDraftRequest(
                question="I was charged twice for one invoice. What happens next?"
            )
        )

        self.assertEqual(response.risk_level, "high")
        self.assertIn("high_risk_intent", response.review_triggers)
        self.assertTrue(response.requires_human_review)
        self.assertEqual(response.review_status, "pending_review")
        self.assertIn(
            "risk_not_low",
            response.generation_metadata.automation_eligibility.reason_codes,
        )

    def test_invalid_assessment_quote_fails_before_generation(self):
        invalid = EvidenceAssessmentProposal(
            requested_information=[
                RequestedInformationAssessment(
                    requested_information="invoice download instructions",
                    finding="supported",
                    answer="An unsupported answer.",
                    evidence=[
                        EvidenceQuote(
                            chunk_id=self.chunk.chunk_id,
                            quote="This quote is not in the source.",
                        )
                    ],
                )
            ],
            supporting_facts=[],
        )
        provider = FakeGenerationProvider(assessment=invalid)
        orchestrator, _ = self.make_orchestrator(provider)

        with self.assertRaisesRegex(DraftGenerationError, "assessment failed"):
            orchestrator.draft_reply(self.payload)

        self.assertEqual(len(provider.structured_calls), 1)
        self.assertEqual(provider.generation_calls, [])

    def test_malformed_assessment_and_provider_failure_are_explicit(self):
        for provider in (
            FakeGenerationProvider(assessment="not JSON"),
            FakeGenerationProvider(
                assessment_error=OllamaProviderError("Ollama unavailable")
            ),
        ):
            with self.subTest(error=provider.assessment_error):
                orchestrator, _ = self.make_orchestrator(provider)

                with self.assertRaisesRegex(
                    DraftGenerationError,
                    "assessment failed",
                ):
                    orchestrator.draft_reply(self.payload)

                self.assertEqual(provider.generation_calls, [])

    def test_truncated_assessor_and_generator_outputs_fail_explicitly(self):
        assessor_provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
            assessment_call_metrics=make_generation_metrics(
                eval_count=1024,
                done_reason="length",
            ),
        )
        orchestrator, _ = self.make_orchestrator(assessor_provider)
        with self.assertRaisesRegex(DraftGenerationError, "assessment output"):
            orchestrator.draft_reply(self.payload)
        self.assertEqual(assessor_provider.generation_calls, [])

        generator_provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
            generation_call_metrics=make_generation_metrics(
                eval_count=256,
                done_reason="length",
            ),
        )
        orchestrator, _ = self.make_orchestrator(generator_provider)
        with self.assertRaisesRegex(DraftGenerationError, "customer response output"):
            orchestrator.draft_reply(self.payload)

    def test_generator_provider_failure_is_explicit(self):
        provider = FakeGenerationProvider(
            assessment=supported_invoice_proposal(self.chunk),
            generation_error=OllamaProviderError("Ollama unavailable"),
        )
        orchestrator, _ = self.make_orchestrator(provider)

        with self.assertRaisesRegex(DraftGenerationError, "generation failed"):
            orchestrator.draft_reply(self.payload)

    def test_malformed_or_blank_structured_reply_is_rejected(self):
        long_output = " ".join(["word"] * 71)
        for output in (
            "not JSON",
            '{"draft": "   "}',
            '{"draft": "Answer", "extra": 1}',
            json.dumps({"draft": long_output}),
            json.dumps({"draft": "One. Two. Three. Four."}),
        ):
            with self.subTest(output=output):
                provider = FakeGenerationProvider(
                    assessment=supported_invoice_proposal(self.chunk),
                    generation_output=output,
                )
                orchestrator, _ = self.make_orchestrator(provider)

                with self.assertRaisesRegex(
                    DraftGenerationError,
                    "malformed structured output",
                ):
                    orchestrator.draft_reply(self.payload)

    def test_flag_off_selects_preview_and_enabled_flag_selects_generator(self):
        retriever = Mock()
        provider = Mock()
        defaults = Settings(_env_file=None)
        self.assertFalse(Settings.model_fields["support_draft_generation_enabled"].default)
        self.assertFalse(Settings.model_fields["support_draft_automation_enabled"].default)
        self.assertFalse(defaults.support_draft_generation_enabled)
        self.assertFalse(defaults.support_draft_automation_enabled)
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                SUPPORT_DRAFT_AUTOMATION_ENABLED=True,
            )
        self.assertIsInstance(
            main.create_support_draft_orchestrator(
                app_settings=defaults,
                retriever=retriever,
                provider=provider,
            ),
            PreviewOnlyDraftOrchestrator,
        )

        enabled = Settings(
            _env_file=None,
            SUPPORT_DRAFT_GENERATION_ENABLED=True,
            SUPPORT_DRAFT_GENERATOR_MODEL="qwen3:4b",
            SUPPORT_DRAFT_GENERATION_MAX_TOKENS=256,
            SUPPORT_DRAFT_AUTOMATION_ENABLED=True,
        )
        self.assertIsInstance(
            main.create_support_draft_orchestrator(
                app_settings=enabled,
                retriever=retriever,
                provider=provider,
            ),
            GeneratedDraftOrchestrator,
        )

    def test_draft_endpoint_persists_generated_assessment_and_metadata(self):
        response = SupportDraftResponse(
            trace_id=str(uuid4()),
            intent="general_support",
            risk_level="low",
            model_used="assessor=qwen3:4b;generator=qwen3:4b",
            draft="An evidence-backed response.",
            citations=[],
            retrieval_confidence=None,
            answer_confidence=None,
            requires_human_review=True,
            review_status="pending_review",
            escalation_reason="generated_pilot_review_first",
            citation_source_ids=[],
            citation_contract_passed=False,
            review_triggers=["generated_pilot_review_first"],
            evidence_assessment={"status": "sufficient", "action": "draft_from_determined_claims"},
            generation_metadata=SupportDraftGenerationMetadata(
                outcome="generated",
                retrieved_chunk_count=1,
                retrieval_top_k=3,
                assessor_model="qwen3:4b",
                assessor_metrics=DraftModelCallMetrics(done=True),
                generator_model="qwen3:4b",
                generator_max_output_tokens=256,
                generation_completion_verified=True,
                total_elapsed_seconds=2.0,
            ),
        )
        repository = Mock()
        with (
            patch.object(main, "orchestrator") as orchestrator,
            patch.object(main, "support_repository", repository),
            patch.object(main.metrics, "record_support_draft") as record_metric,
        ):
            orchestrator.draft_reply.return_value = response
            returned = main.draft_support_reply(self.payload)

        self.assertEqual(returned, response)
        repository.save_support_draft.assert_called_once_with(
            draft_request=self.payload,
            draft_response=response,
        )
        record_metric.assert_called_once_with(requires_human_review=True)

    def test_draft_endpoint_maps_generation_error_without_saving_success(self):
        repository = Mock()
        with (
            patch.object(main, "orchestrator") as orchestrator,
            patch.object(main, "support_repository", repository),
        ):
            orchestrator.draft_reply.side_effect = DraftGenerationError(
                "Customer-response generation failed."
            )
            with self.assertRaises(HTTPException) as raised:
                main.draft_support_reply(self.payload)

        self.assertEqual(raised.exception.status_code, 502)
        repository.save_support_draft.assert_not_called()


if __name__ == "__main__":
    unittest.main()
