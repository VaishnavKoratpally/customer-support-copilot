from app.schemas import Citation


def build_support_system_prompt() -> str:
    return (
        "You are a customer support copilot. "
        "Answer only using provided evidence. "
        "If evidence is insufficient, say so clearly and request human review. "
        "Do not invent policies."
    )


def build_support_user_prompt(*, question: str, intent: str, citations: list[Citation]) -> str:
    evidence_block = "\n".join(
        f"- [{c.source_id}] {c.title}: {c.excerpt}" for c in citations
    )
    return (
        f"Intent: {intent}\n"
        f"Customer question: {question}\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Produce a concise draft response aligned to evidence."
    )