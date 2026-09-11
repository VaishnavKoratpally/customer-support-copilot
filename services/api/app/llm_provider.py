class StubLLMProvider:
    """
    Week 1 placeholder model provider.
    Uses deterministic drafting so orchestration and policy logic can be tested first.
    """

    def draft_response(self, *, question: str, intent: str, model_name: str) -> str:
        if intent == "billing_dispute":
            return (
                "Thanks for flagging this. I can see this may be a billing dispute. "
                "I have prepared the case for billing review and will prioritize it. "
                "You can expect an update within 2 business days."
            )

        return (
            "Thanks for reaching out. I have prepared a support draft based on our current guidance. "
            "If you share any additional details, I can refine next steps."
        )

