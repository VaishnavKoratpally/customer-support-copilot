# ADR-008: Requested-information evidence assessment and draft gating

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
customer-facing draft. Some questions request a value, such as a duration,
rather than asserting a proposition. The assessment must represent that
requested information separately from an answer so it does not repeat the
question as a claim or invent a missing value. Billing and account-security
responses may still require human review even when their evidence is
sufficient.

## Decision

- Assess each atomic piece of requested information after retrieval and before
  draft generation.
- Use a local language model to propose findings and evidence references. Do
  not accept an overall action or confidence score from the model.
- One schema-constrained call receives the customer question and retrieved
  chunks. For each requested fact or value, it returns a concise
  `requested_information` label, an evidence finding, and an `answer` only
  when the evidence determines one. It separately returns directly relevant,
  supported response facts that may help explain a limitation without being
  mistaken for answers to the requested information. Measure omitted or
  merged request parts in evaluation.
- Configure the assessor independently through `EVIDENCE_ASSESSOR_MODEL`,
  initially defaulting to `qwen3:4b`; do not couple it to the router or draft
  model setting. This is an initial experiment, not a claim that the model
  meets the evidence-accuracy target.
- Pass `EvidenceAssessmentProposal`'s JSON Schema through Ollama's structured
  output `format` parameter, then validate again with Pydantic and the
  deterministic evidence validator. Prompt-only JSON instructions are not a
  validation boundary. Answers are required for `supported` and `contradicted`
  requested information and must be declarative; undetermined requests must
  have a null answer. Supporting response facts must be marked `supported`,
  cite exact retrieved text, and not duplicate a determined answer.
- Each requested-information finding is one of:
  - `supported`: retrieved text determines an answer to the requested
    information.
  - `contradicted`: retrieved text establishes that an explicitly
    asked-about proposition is false, and the answer states what the evidence
    establishes instead.
  - `related_but_not_supported`: related text exists but does not establish the
    requested fact.
  - `no_relevant_evidence`: no retrieved chunk is relevant to the requested
    fact.
  - `conflicting`: retrieved sources make incompatible claims.
- Supported and contradicted findings must include a declarative answer and
  cite at least one retrieved chunk with a verbatim quote.
  Related-but-not-supported findings must identify relevant context and have
  no answer; no-relevant-evidence findings must have no quotes or answer.
  Conflicting findings must quote at least two distinct retrieved chunks and
  have no answer. Supporting response facts must be supported by at least one
  retrieved chunk with a verbatim quote. The application validates chunk IDs
  and exact quote substrings before accepting the assessment.
- Compute the aggregate status and action deterministically:
  - `sufficient`: every requested item has a supported or contradicted
    answer; draft from those determined answers.
  - `partial`: at least one requested item is undetermined, but another
    requested item has a determined answer or a directly relevant supporting
    fact is supported; draft only determined answers and validated supporting
    facts, state the limitation, and escalate for review.
  - `insufficient`: no requested item has a determined answer and no helpful
    supporting fact is available, but related context exists; state that the
    requested information could not be determined from the available guidance
    and escalate.
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

## Current runtime boundary: Stage A (2026-10-14)

The generation design above is not a certification that the local assessor
is accurate enough to authorize customer-facing drafts. Development status
agreement remains 3/5, and the small held-out run does not establish semantic
coverage or safe generalization. Do not chase development 5/5 as a release
proof or weaken the validators to obtain it.

The implemented next slice is separate, opt-in reviewer evidence assistance
on saved preview traces. It makes at most one application model call for a
newly reserved request UUID, records either a proposal or explicit failure,
and exposes the original passages and separate reviewer feedback. Same-ID
replay never requests another inference; new IDs deliberately create new
attempts. Reservation commits before inference, avoiding a database
transaction across the model call.

All successful reads identify the result as an unverified advisory proposal.
Its derived status/action is metadata, not an instruction executed by the
support workflow. Exact quote checks prove provenance only, not applicability
or entailment. Feedback can document omitted requests, unsupported answers,
missing conditions, and clarification problems; it is neither draft approval
nor automatically trusted gold.

`/v1/support/draft` remains retrieval-preview-only, with unknown confidence
and mandatory human review. Assistance and feedback cannot change review or
simulated-delivery eligibility. Future generated-answer integration still
requires independent semantic evaluation and the generation gate in this ADR.
This slice has no authenticated reviewer authorization, queue, or crash
recovery worker; a reserved attempt may remain running after interruption.
Prompt/schema hashes and the configured model tag distinguish attempts but
are not immutable model-digest provenance.

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
4. Use a local-model evidence assessment with deterministic validation and
   status-to-action mapping. Chosen; this balances semantic flexibility with
   explicit application policy.

## Tradeoffs

- Benefits:
  - separates candidate retrieval from factual support decisions
  - preserves the requested fact/value separately from its evidence-backed
    answer
  - makes status aggregation and safe actions deterministic and unit-testable
  - allows partial answers without treating the whole query as all-or-nothing
  - permits independent assessor model experiments without changing routing or
    drafting configuration
  - Costs:
    - adds a model call and latency before draft generation
    - requires structured output validation and an expanded evaluation set
    - exact quote checks verify text provenance, not semantic entailment
    - a single call can omit or merge a multi-part request, or confuse a
      supporting fact with a determined answer; labeled evaluation must
      measure requested-information coverage and false-sufficient decisions
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
- Requested information is distinct from determined answers and supporting
  facts; answer propositions and supporting facts must be evidence-backed.
- Before runtime draft integration, the fixed evaluation set has no
  false-sufficient outcomes for partial, insufficient, none,
  clarification-needed, or conflicting cases.
- Mandatory human-review compliance remains 100% for high-risk intents.
