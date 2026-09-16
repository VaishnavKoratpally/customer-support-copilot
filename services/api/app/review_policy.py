from dataclasses import dataclass
from typing import Literal


ReviewTrigger = Literal["high_risk_intent", "low_answer_confidence", "missing_citations"]

HIGH_RISK_INTENTS = {
    "billing_dispute",
    "account_security",
    "legal",
}


@dataclass(frozen=True)
class ReviewDecision:
    requires_human_review: bool
    triggers: list[ReviewTrigger]


def evaluate_review_policy(
    *,
    intent: str,
    answer_confidence: float,
    answer_confidence_threshold: float,
    citation_contract_passed: bool,
) -> ReviewDecision:
    triggers: list[ReviewTrigger] = []

    if intent in HIGH_RISK_INTENTS:
        triggers.append("high_risk_intent")
    if answer_confidence < answer_confidence_threshold:
        triggers.append("low_answer_confidence")
    if not citation_contract_passed:
        triggers.append("missing_citations")

    return ReviewDecision(
        requires_human_review=len(triggers) > 0,
        triggers=triggers,
    )