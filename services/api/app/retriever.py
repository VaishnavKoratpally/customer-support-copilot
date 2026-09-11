from dataclasses import dataclass

from app.schemas import Citation


@dataclass(frozen=True)
class RetrievalResult:
    citations: list[Citation]
    confidence: float


class StubRetriever:
    """Week 1 placeholder retriever with deterministic outputs."""

    def retrieve(self, question: str, top_k: int = 3) -> RetrievalResult:
        normalized = question.lower()

        if "charged twice" in normalized or "refund" in normalized:
            return RetrievalResult(
                citations=[
                    Citation(
                        source_id="billing-policy-01",
                        title="Billing and Refund Policy",
                        excerpt="Duplicate charges are reviewed within 2 business days and reversed if confirmed.",
                    ),
                    Citation(
                        source_id="support-sla-02",
                        title="Support SLA",
                        excerpt="Billing disputes require human review for final resolution.",
                    ),
                ][:top_k],
                confidence=0.82,
            )

        return RetrievalResult(
            citations=[
                Citation(
                    source_id="general-help-01",
                    title="General Support Playbook",
                    excerpt="Ask clarifying questions and provide concrete next steps with expected timelines.",
                )
            ][:top_k],
            confidence=0.61,
        )

