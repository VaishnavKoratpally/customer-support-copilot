from typing import Literal

RejectionReasonCode = Literal[
    "policy-risk",
    "missing-citations",
    "incorrect-facts",
    "tone-issue",
    "needs-human-judgment",
    "insufficient-context",
]

VALID_REJECTION_REASONS = {
    "policy-risk",
    "missing-citations",
    "incorrect-facts",
    "tone-issue",
    "needs-human-judgment",
    "insufficient-context",
}