# ADR-008: Claim-level evidence assessment and draft gating

Date: 2026-10-08  
Status: Accepted

## Context

The pgvector retriever returns the nearest eligible chunks and raw cosine
distances. A nearest chunk can be topically related without supporting the
specific fact requested, and an empty expected-source label does not mean the
retriever returns no candidates. Cosine distance is therefore not an evidence
sufficiency score.

The support-draft path needs to distinguish answerable questions from partial,
unsupported, ambiguous, and conflicting evidence before generating a
customer-facing draft. Billing and account-security responses may still require
human review even when their evidence is sufficient.

## Decision

- Assess evidence claim by claim after retrieval and before draft generation.
- Use a local language model to propose findings and evidence references. Do
  not accept an overall action or confidence score from the model.
- Each claim finding is one of:
  - `supported`: retrieved text supports the requested answer claim.
  - `contradicted`: retrieved text supports the opposite of the claim.
  - `related_but_not_supported`: related text exists but does not establish the
    requested fact.
  - `no_relevant_evidence`: no retrieved chunk is relevant to the requested
    fact.
  - `conflicting`: retrieved sources make incompatible claims.
- Supported and contradicted findings must cite at least one retrieved chunk
  with a verbatim quote. Related-but-not-supported findings must identify
  relevant context. Conflicting findings must quote at least two distinct
  retrieved chunks. The application validates chunk IDs and exact quote
  substrings before accepting the assessment.
- Compute the aggregate status and action deterministically:
  - `sufficient`: every requested claim is supported or contradicted; draft
    from the determined claims.
  - `partial`: at least one claim is determined and at least one is not; draft
    only the determined claims, state the limitation, and escalate for review.
  - `insufficient`: no claim is determined, but related context exists; state
    that the requested fact is not specified and escalate.
  - `none`: no relevant evidence exists, even if nearest-neighbor search
    returned candidates; return an explicit abstention/review outcome without
    a substantive customer-facing draft.
  - `clarification_needed`: request clarification before selecting an answer
    path.
  - `conflicting`: do not draft a substantive answer; require human review.
- Keep risk-based human-review policy separate from evidence sufficiency.
  Sufficient evidence does not waive mandatory review for high-risk intents.
- Do not map cosine distance or model self-reported confidence to evidence
  sufficiency.
- If the assessor is unavailable or returns malformed output, unknown chunk
  IDs, or invalid quotes, fail closed: do not draft and return an explicit API
  error. Do not fall back to `StubRetriever`.

## Options Considered

1. Use a cosine-distance cutoff as the sufficiency decision. Rejected because
   topical but incomplete questions can have close matches, and unsupported
   questions still receive nearest candidates.
2. Use deterministic keyword/domain rules only. Rejected for the first runtime
   version because the current policies are unstructured text and paraphrases
   make exhaustive rules brittle.
3. Let the draft model generate an answer and self-certify it in one pass.
   Rejected as the only safeguard because unsupported claims and assessment
   errors could share the same model failure.
4. Use a local-model claim assessment with deterministic validation and
   status-to-action mapping. Chosen; this balances semantic flexibility with
   explicit application policy.

## Tradeoffs

- Benefits:
  - separates candidate retrieval from factual support decisions
  - preserves which evidence supports each requested claim
  - makes status aggregation and safe actions deterministic and unit-testable
  - allows partial answers without treating the whole query as all-or-nothing
- Costs:
  - adds a model call and latency before draft generation
  - requires structured output validation and an expanded evaluation set
  - exact quote checks verify text provenance, not semantic entailment
- Risks:
  - the local assessor can miss support, overstate support, or misclassify
    conflicting evidence
  - an assessor and draft model from the same family may have correlated
    failures
  - false-sufficient decisions are more harmful than conservative
    abstentions; human review and evaluation remain necessary

## Rollback Trigger

If evaluation finds unacceptable false-sufficient decisions or invalid
assessments that cannot be mitigated, disable draft generation from assessed
evidence and route requests to explicit manual handling. Do not restore a
success-shaped stub fallback.

## Validation Metrics

- Deterministic aggregation tests cover every aggregate status and action.
- Invalid evidence references and non-verbatim quotes fail closed.
- Before runtime draft integration, the fixed evaluation set has no
  false-sufficient outcomes for partial, insufficient, none,
  clarification-needed, or conflicting cases.
- Mandatory human-review compliance remains 100% for high-risk intents.
