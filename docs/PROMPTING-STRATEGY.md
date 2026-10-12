# Prompting Strategy v1 (Day 4)

## Objective

Define a deterministic, evidence-first prompting approach for support draft generation so outputs are:

- grounded in retrieved sources,
- safe for human-in-the-loop review,
- consistent across model upgrades.

## Scope

This strategy applies to the support draft flow:

- Endpoint: `POST /v1/support/draft`
- Planned generated-answer orchestration: route -> retrieve -> prompt -> draft -> policy gate.
- Current runtime: preview-only; it retrieves evidence and abstains without calling a model.

The prompt templates below describe a future generated-answer path. They are
not currently invoked by `/v1/support/draft`. Generation remains gated on the
evidence assessor meeting the acceptance criteria in
[ADR-008](./adr/008-claim-level-evidence-assessment.md).

## Prompt architecture

### 1) System prompt (policy-level instruction)

Purpose:
- set role and boundaries for the model.
- define non-negotiable behavior constraints.

v1 constraints:
1. Use only provided evidence.
2. If evidence is insufficient, explicitly say so.
3. Do not invent policy details or outcomes.
4. Prefer concise, operationally actionable language.

### 2) User prompt (request + evidence payload)

Purpose:
- provide request context and structured evidence.
- reduce ambiguity by explicitly labeling intent and source excerpts.

v1 structure:
- `Intent`
- `Customer question`
- `Evidence` list in `[source_id] title: excerpt` format
- final instruction to produce concise evidence-aligned draft

## Why this design

1. Separation of concerns:
   - system prompt governs behavior policy
   - user prompt carries case-specific content

2. Reproducibility:
   - deterministic prompt shape supports debugging and eval comparisons.

3. Auditability:
   - evidence appears in prompt payload, making grounding checks easier.

## Tradeoffs

### Pros
- simpler debugging and incident review
- easier to evaluate groundedness regressions
- safer baseline for HITL workflows

### Cons
- rigid format can reduce stylistic flexibility
- may underperform if retrieved evidence is sparse/noisy
- requires citation quality to be good, or prompt quality degrades

## Failure modes to watch

1. **Evidence mismatch**  
   Retrieved snippets are irrelevant, yet output sounds confident.

2. **Instruction drift**  
   Model generates extra policy claims not present in evidence.

3. **Over-compression**  
   Output is concise but omits critical operational details.

4. **False confidence language**  
   Draft implies certainty when evidence is incomplete.

## Planned guardrails linked to prompting

- mandatory human review for high-risk intents
- human review when answer confidence is below threshold
- human review when citations are missing or weak
- escalation reason captured in response payload

The current preview-only runtime does not invoke these prompt or confidence
policies; it always abstains and requires review. The generated-answer guardrails
become active only when generation is enabled after the evidence-assessment
gate passes.

## Evolution plan

### Prepared prompt contract (not active in the runtime)
- static system/user prompt templates
- response must include citation_source_ids
- citation_contract_passed must be true for normal flow
- missing citations forces HITL with escalation reason

### v1.1
- add explicit citation rendering format in output contract
- add prompt version tagging for eval tracking

### v1.2
- route-specific prompt variants (billing dispute vs general support)
- stricter refusal pattern for insufficient evidence

## Success criteria linkage

Prompting quality is considered acceptable when:
- groundedness pass rate meets target,
- citation correctness meets target,
- hallucination rate stays below threshold,
- human reviewers report low unsupported-claim frequency.