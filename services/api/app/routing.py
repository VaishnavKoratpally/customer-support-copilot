from dataclasses import dataclass
from typing import Literal
from app.query_rules import is_billing_dispute_question


RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class RoutingDecision:
    intent: str
    risk_level: RiskLevel


def route_question(question: str) -> RoutingDecision:
    normalized = question.lower()

    high_risk_keywords = {
        "hacked": "account_security",
        "unauthorized": "account_security",
        "lawyer": "legal",
        "legal": "legal",
    }
    if is_billing_dispute_question(question):
        return RoutingDecision(intent="billing_dispute", risk_level="high")
    for keyword, intent in high_risk_keywords.items():
        if keyword in normalized:
            return RoutingDecision(intent=intent, risk_level="high")

    medium_risk_keywords = {
        "cancel": "subscription_change",
        "downgrade": "subscription_change",
        "upgrade": "subscription_change",
    }
    for keyword, intent in medium_risk_keywords.items():
        if keyword in normalized:
            return RoutingDecision(intent=intent, risk_level="medium")

    return RoutingDecision(intent="general_support", risk_level="low")

