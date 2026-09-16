from typing import Literal


RiskLevel = Literal["low", "medium", "high"]


def compute_answer_confidence(*, retrieval_confidence: float, risk_level: RiskLevel) -> float:
    risk_bias = 0.2 if risk_level == "low" else 0.1
    score = (retrieval_confidence * 0.7) + risk_bias
    return round(score, 2)