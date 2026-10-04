DUPLICATE_SIGNALS = (
    "charged twice",
    "two charges",
    "duplicate",
    "double payment",
    "two transactions",
)

BILLING_CONTEXT_TERMS = (
    "charge",
    "charged",
    "billing",
    "invoice",
    "renewal",
    "payment",
    "transaction",
    "subscription",
)


def is_billing_dispute_question(question: str) -> bool:
    normalized = " ".join(question.casefold().split())

    if "refund" in normalized:
        return True

    has_duplicate_signal = any(signal in normalized for signal in DUPLICATE_SIGNALS)
    has_billing_context = any(term in normalized for term in BILLING_CONTEXT_TERMS)
    return has_duplicate_signal and has_billing_context