import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from app.evidence_assessment import EvidenceAssessmentDecision, EvidenceQuote
from app.retrieval_repository import RetrievedChunk
from app.schemas import FAQAutomationBlockReason, FAQAutomationEligibility, FAQFinalResponseChecks


APPROVED_FAQ_SOURCE_ID = "billing-invoice-faq-01"
APPROVED_FAQ_POLICY_VERSION = "week4-synthetic-v1"
APPROVED_FAQ_EFFECTIVE_DATE = date(2026, 10, 14)
APPROVED_FAQ_ACCESS_SCOPE = "public"
APPROVED_FAQ_CONTENT_SHA256 = (
    "ef564a2a5055c8a9e8faeaaf0f3bfebccfc4559f1528d678bba10d06738c32cc"
)

FAQFamily = Literal["invoice_copy_instructions", "invoice_field_explanations"]

_INVOICE = re.compile(r"\binvoices?\b")
_COPY_REQUEST = re.compile(
    r"\b(?:download|pdf|copies?|csv|export|email(?:ed|ing)?|roles?|owners?|members?)\b"
)
_FIELD_NUMBER = re.compile(
    r"\b(?:invoice number|account number|proof of payment|payment status)\b"
)
_FIELD_PERIOD = re.compile(r"\b(?:billing period|charge period|payment due|due date)\b")
_FIELD_CURRENCY = re.compile(r"\b(?:currency|exchange rate|denomination)\b")

_OUT_OF_SCOPE_REQUEST = re.compile(
    r"\b(?:csv|email(?:ed|ing)?|refund|chargeback|charged twice|duplicate charge|"
    r"cancel|bypass|grant|revoke|modify|change|process)\b"
    r"|\b(?:can|could|would)\s+you\s+"
    r"(?:download|retrieve|send|email|access|grant|change|cancel|refund|process)\b"
    r"|\b(?:please|just)\s+(?:retrieve|send|email|access)\b"
    r"|\b(?:what is|what's|tell me|show me|look up|get me)\b"
    r".{0,40}\bmy invoice number\b"
    r"|\b(?:bypass|grant|change|modify|revoke)\b.{0,40}"
    r"\b(?:role|access|permission|billing admin)\b",
    re.IGNORECASE,
)
_ACTION_CLAIM = re.compile(
    r"\b(?:i|we)\s+(?:(?:am|are|have|has|already|will|can|did)\s+){0,3}"
    r"(?:download(?:ed|ing)?|retriev(?:e|ed|ing)|send|sent|email(?:ed|ing)?|"
    r"access(?:ed|ing)?|grant(?:ed|ing)?|change(?:d|ing)?|cancel(?:ed|led|ling)?|"
    r"process(?:ed|ing)?|refund(?:ed|ing)?|approv(?:e|ed|ing)|"
    r"confirm(?:ed|ing)?|verif(?:y|ied|ying)|guarantee)\b",
    re.IGNORECASE,
)
_INTERNAL_IDENTIFIER = re.compile(
    r"\b(?:source_id|chunk_id|requested_information|supporting_facts|"
    r"qwen3(?::|[- ])|week4-synthetic-v1|billing-invoice-faq-01)\b"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_MEMBER_CANNOT_DOWNLOAD = re.compile(
    r"\b(?:regular\s+)?(?:workspace\s+)?members?\b[^.!?]{0,60}"
    r"\b(?:cannot|can't|can not|unable|not able)\b[^.!?]{0,60}\bdownload\b",
    re.IGNORECASE,
)
_NEGATED_DUE_DATE = re.compile(
    r"\b(?:not|isn't|doesn't|does not)\b[^.!?]{0,60}"
    r"\b(?:payment due|due date|payment deadline)\b"
    r"|\b(?:payment due|due date|payment deadline)\b[^.!?]{0,60}"
    r"\b(?:not|isn't|doesn't|does not)\b",
    re.IGNORECASE,
)
_NEGATED_EXCHANGE_RATE = re.compile(
    r"\b(?:not|isn't|doesn't|does not)\b[^.!?]{0,60}\bexchange rate\b"
    r"|\bexchange rate\b[^.!?]{0,60}\b(?:not|isn't|doesn't|does not)\b",
    re.IGNORECASE,
)
_NEGATED_PAYMENT_PROOF = re.compile(
    r"\b(?:not|isn't|doesn't|does not)\b[^.!?]{0,60}"
    r"\b(?:proof|payment|paid)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FAQAutomationEvaluation:
    checks: FAQFinalResponseChecks
    eligibility: FAQAutomationEligibility


def response_within_output_contract(text: str) -> bool:
    normalized = text.strip()
    if not normalized or len(normalized.split()) > 70:
        return False
    sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]
    return len(sentences) <= 3


def evaluate_faq_automation_eligibility(
    *,
    question: str,
    risk_level: str,
    assessment: EvidenceAssessmentDecision | None,
    retrieved_chunks: Sequence[RetrievedChunk],
    draft: str,
    generation_completion_verified: bool | None,
) -> FAQAutomationEvaluation:
    families = _recognized_families(question)
    topics = _requested_topics(question, families)
    labels = (
        [item.requested_information.casefold() for item in assessment.requested_information]
        if assessment is not None
        else []
    )
    citations = list(_assessment_quotes(assessment))
    chunk_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
    evidence_chunks = {
        quote.chunk_id: chunk_by_id[quote.chunk_id]
        for quote in citations
        if quote.chunk_id in chunk_by_id
    }
    evidence_provenance_valid = _evidence_provenance_is_valid(
        assessment=assessment,
        chunk_by_id=chunk_by_id,
    )
    evidence_source_approved = bool(citations) and len(evidence_chunks) == len(
        {quote.chunk_id for quote in citations}
    ) and all(
        chunk.source_id == APPROVED_FAQ_SOURCE_ID
        and chunk.policy_version == APPROVED_FAQ_POLICY_VERSION
        and chunk.effective_date == APPROVED_FAQ_EFFECTIVE_DATE
        and chunk.access_scope == APPROVED_FAQ_ACCESS_SCOPE
        and chunk.source_checksum_sha256 == APPROVED_FAQ_CONTENT_SHA256
        for chunk in evidence_chunks.values()
    )
    allowed_sections = {
        "Invoice copies"
        for family in families
        if family == "invoice_copy_instructions"
    } | {
        "Invoice fields"
        for family in families
        if family == "invoice_field_explanations"
    }
    evidence_sections_match = (
        bool(evidence_chunks)
        and bool(allowed_sections)
        and all(chunk.section_path in allowed_sections for chunk in evidence_chunks.values())
    )
    assessment_is_sufficient = (
        assessment is not None
        and assessment.status == "sufficient"
        and bool(assessment.requested_information)
        and all(
            item.finding in {"supported", "contradicted"}
            and item.answer is not None
            for item in assessment.requested_information
        )
    )
    topics_are_covered = bool(topics) and all(
        _topic_is_assessed(topic, labels) for topic in topics
    )
    response_is_complete = (
        response_within_output_contract(draft)
        and generation_completion_verified is not False
    )
    question_has_out_of_scope_content = bool(_OUT_OF_SCOPE_REQUEST.search(question))
    checks = FAQFinalResponseChecks(
        retrieved_evidence_present=bool(retrieved_chunks),
        response_complete=response_is_complete,
        request_is_low_risk=risk_level == "low",
        approved_faq_family_recognized=bool(families),
        request_topics_covered=topics_are_covered,
        assessment_status_sufficient=assessment_is_sufficient,
        evidence_provenance_valid=evidence_provenance_valid,
        source_version_and_content_approved=evidence_source_approved,
        evidence_sections_match_request=evidence_sections_match,
        required_conditions_preserved=_required_conditions_preserved(
            question=question,
            families=families,
            topics=topics,
            draft=draft,
        ),
        no_prohibited_action_claims=not bool(_ACTION_CLAIM.search(draft)),
        no_internal_identifiers=not bool(_INTERNAL_IDENTIFIER.search(draft)),
    )
    reason_by_check: tuple[
        tuple[bool, FAQAutomationBlockReason], ...
    ] = (
        (checks.retrieved_evidence_present, "no_retrieved_evidence"),
        (checks.request_is_low_risk, "risk_not_low"),
        (checks.approved_faq_family_recognized, "request_family_not_approved"),
        (not question_has_out_of_scope_content, "out_of_scope_request"),
        (checks.request_topics_covered, "request_coverage_unverified"),
        (checks.assessment_status_sufficient, "assessment_not_sufficient"),
        (checks.evidence_provenance_valid, "evidence_provenance_invalid"),
        (
            checks.source_version_and_content_approved,
            "source_version_or_content_not_approved",
        ),
        (checks.evidence_sections_match_request, "evidence_section_mismatch"),
        (checks.required_conditions_preserved, "required_condition_missing"),
        (checks.no_prohibited_action_claims, "prohibited_action_claim"),
        (checks.response_complete, "response_incomplete"),
        (checks.no_internal_identifiers, "internal_identifier_in_response"),
    )
    reasons = [reason for passed, reason in reason_by_check if not passed]
    eligibility = FAQAutomationEligibility(
        eligible_candidate=not reasons,
        reason_codes=reasons,
    )
    return FAQAutomationEvaluation(checks=checks, eligibility=eligibility)


def _recognized_families(question: str) -> frozenset[FAQFamily]:
    normalized = " ".join(question.casefold().split())
    has_invoice = bool(_INVOICE.search(normalized))
    families: set[FAQFamily] = set()
    if has_invoice and _COPY_REQUEST.search(normalized):
        families.add("invoice_copy_instructions")
    has_field_context = "field" in normalized or has_invoice
    if has_field_context and any(
        pattern.search(normalized)
        for pattern in (_FIELD_NUMBER, _FIELD_PERIOD, _FIELD_CURRENCY)
    ):
        families.add("invoice_field_explanations")
    return frozenset(families)


def _requested_topics(
    question: str,
    families: frozenset[FAQFamily],
) -> frozenset[str]:
    normalized = " ".join(question.casefold().split())
    topics: set[str] = set()
    if "invoice_copy_instructions" in families:
        if re.search(r"\b(?:download|pdf|copies?|where do i find)\b", normalized):
            topics.add("copy_steps")
        if re.search(
            r"\b(?:roles?|owners?|members?|billing admins?|authorized|permissions?)\b",
            normalized,
        ):
            topics.add("copy_roles")
    if "invoice_field_explanations" in families:
        if _FIELD_NUMBER.search(normalized):
            topics.add("field_number")
        if _FIELD_PERIOD.search(normalized):
            topics.add("field_period")
        if _FIELD_CURRENCY.search(normalized):
            topics.add("field_currency")
    return frozenset(topics)


def _topic_is_assessed(topic: str, labels: Sequence[str]) -> bool:
    label_patterns = {
        "copy_steps": re.compile(r"\b(?:download|pdf|copy|navigation|path)\b"),
        "copy_roles": re.compile(r"\b(?:role|owner|billing admin|member|permission)\b"),
        "field_number": re.compile(
            r"\b(?:invoice number|account number|payment|proof|paid)\b"
        ),
        "field_period": re.compile(
            r"\b(?:billing period|charge period|due date|payment deadline)\b"
        ),
        "field_currency": re.compile(r"\b(?:currency|exchange rate|denomination)\b"),
    }
    pattern = label_patterns[topic]
    return any(pattern.search(label) for label in labels)


def _assessment_quotes(
    assessment: EvidenceAssessmentDecision | None,
) -> Iterable[EvidenceQuote]:
    if assessment is None:
        return ()
    return (
        quote
        for item in (*assessment.requested_information, *assessment.supporting_facts)
        for quote in item.evidence
    )


def _evidence_provenance_is_valid(
    *,
    assessment: EvidenceAssessmentDecision | None,
    chunk_by_id: dict[UUID, RetrievedChunk],
) -> bool:
    if assessment is None or not assessment.requested_information:
        return False
    for item in assessment.requested_information:
        if item.finding in {"supported", "contradicted"} and not item.evidence:
            return False
    if any(not fact.evidence for fact in assessment.supporting_facts):
        return False
    quotes = tuple(_assessment_quotes(assessment))
    return bool(quotes) and all(
        quote.chunk_id in chunk_by_id
        and quote.quote in chunk_by_id[quote.chunk_id].text
        for quote in quotes
    )


def _required_conditions_preserved(
    *,
    question: str,
    families: frozenset[FAQFamily],
    topics: frozenset[str],
    draft: str,
) -> bool:
    normalized = " ".join(draft.casefold().split())
    question_normalized = question.casefold()
    if "invoice_copy_instructions" in families:
        if not (
            "only" in normalized
            and re.search(r"\bworkspace owners?\b", normalized)
            and re.search(r"\bbilling admins?\b", normalized)
            and re.search(r"\bauthoriz\w*\b", normalized)
            and re.search(r"\bissued invoices?\b", normalized)
        ):
            return False
        if "copy_steps" in topics and not (
            "sign in" in normalized
            and "billing > invoices" in normalized
            and "select" in normalized
            and "download pdf" in normalized
        ):
            return False
        if (
            "copy_roles" in topics
            and re.search(r"\bmembers?\b", question_normalized)
            and not _MEMBER_CANNOT_DOWNLOAD.search(normalized)
        ):
            return False
    if "field_number" in topics and not (
        "invoice number" in normalized
        and "document" in normalized
        and "account number" in normalized
        and "payment" in normalized
        and _NEGATED_PAYMENT_PROOF.search(normalized)
    ):
        return False
    if "field_period" in topics and not (
        "billing period" in normalized
        and "charges" in normalized
        and _NEGATED_DUE_DATE.search(normalized)
    ):
        return False
    if "field_currency" in topics and not (
        "currency" in normalized
        and ("denomination" in normalized or "unit" in normalized)
        and _NEGATED_EXCHANGE_RATE.search(normalized)
    ):
        return False
    return bool(families and topics)
