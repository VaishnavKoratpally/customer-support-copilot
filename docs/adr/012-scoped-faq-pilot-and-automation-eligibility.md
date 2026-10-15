# ADR-012: Scoped FAQ generation and automation eligibility

Date: 2026-10-14
Status: Accepted; review-first generation and deterministic candidate eligibility are implemented. End-to-end evaluation, promotion, and automation enablement remain pending.

## Context

The current live draft path is the [ADR-011 preview](./011-preview-only-draft-retrieval.md).
Advisory assessment and feedback do not authorize customer replies. The
assessor's small evaluations do not establish semantic reliability; exact
quotes establish provenance, not correct meaning or complete request coverage.

The existing corpus is internal and every Week 3 case expects review. It
cannot demonstrate useful low-risk automation. The learner approved a narrow
informational pilot rather than more assessor-status tuning or blanket billing
automation.

## Decision


- Two families: **invoice-copy instructions** and **invoice-field explanations**.
  These explain a fictional SaaS; they do not retrieve an invoice or change it.
- The [synthetic public FAQ](../../data/support_corpus/week4/billing-invoice-faq-01.json)
  and its role, workspace, issued-invoice, format, and field-definition facts.
  `public` means customer-facing inside the local demo only, not suitable for
  real customers. Metadata and content are pinned in the
  [pilot contract](../evals/faq-pilot-contract-v1.json).
- `qwen3:4b` as the first generator baseline, also used by the existing assessor.
  Keep their configuration boundaries separate. This choice avoids deliberate
  switching to a larger model but is not evidence of response quality or
  guaranteed model residency.
- Initial generated replies remain review-first. Default flag-off behavior
  remains preview-only. Neither advisory feedback nor an assessment status
  changes this handling.
- After end-to-end quality/failure/latency gates pass, and only with explicit
  learner enablement, the approved FAQ pilot may authorize eligible replies
  without human review. No real delivery is introduced.

### Scoped eligibility policy

No-review requires a positive decision for the **whole request**, not a
low-risk fallback or one answerable fragment:

1. Recognized informational request within the approved families, with no
   private-data lookup, action, financial dispute, security issue, ambiguity,
   or unsupported part.
2. Support from the approved public source/version/content. Internal,
   restricted, unapproved, or incompatible evidence cannot support automatic
   replies and must not leak through the generated pilot.
3. Valid assessment/provenance and a complete final response with required
   facts and conditions, correct attribution, and no prohibited claims.
   `sufficient` is a fallible signal, not authorization.
4. Tested final-response guards and approved end-to-end evaluation. Mechanical
   quote checks alone do not meet this requirement. Document what is checked
   deterministically versus what remains semantic evaluation; if adequate
   conservative guards cannot be implemented, retain review-first handling.
5. An explicit pilot enablement decision and consistent persisted review/
   delivery state. Failed or unvalidated outcomes cannot become successful
   automatic replies.

| Request class | Initial generated pilot | After approved promotion |
|---|---|---|
| Fully supported invoice-copy/field FAQ with valid final reply | Pending review; candidate eligibility separate | May be `not_required` |
| Financial dispute, security, private-data lookup, or action | Human review; no automatic action | Human review |
| Unsupported or ambiguous request | Clarify/abstain with review | Clarify/abstain with review |
| Conditional/multipart request containing an unsupported action or fact | Limited supported guidance only if validated; review | Review |
| Malformed, truncated, invalid-provenance, or provider-failed outcome | Explicit failure; no successful-looking fallback | No automatic handling |

Unknown confidence remains `NULL`. The scoped policy does **not** manufacture
a score or lower the [ADR-005 thresholds](./005-routing-threshold-defaults.md).
Legacy numerical policy remains unchanged; a future generated FAQ path must
use an explicit eligibility decision instead of feeding invented confidence
into that policy. Mandatory risk/review boundaries are preserved.

For this pilot only, the release criterion is independent semantic evaluation
of captured final replies plus the contract's safety and performance gates,
not development 5/5 assessor-status agreement. This qualifies the future
generation authorization in [ADR-008](./008-claim-level-evidence-assessment.md)
and ADR-011; it does not permit general generated answers or change the
current preview runtime. The contract/case approval state must be checked
before evaluation or tuning starts.

### Evaluation contract

- At least eight [development cases](../evals/faq-pilot-development-v1.jsonl)
  and eight separate [held-out cases](../evals/faq-pilot-heldout-v1.jsonl).
  Each split includes four eligible positives and high-risk, unsupported,
  ambiguous, and conditional/multipart negatives.
- The contract supplies semantic facts, conditions, prohibited claims, source
  fingerprints, route expectations, rubric, and metric denominators.
  Fact IDs describe expectations, not a whitelist of test-question strings
  or proof that a generated claim is correct.
- Evaluate retrieval, citations, meaning, coverage, routing, and latency on
  the **same captured response**. Manually review every generated response
  in these small release sets; future eligible runtime requests do not each
  require a manual assessment-feedback step.
- Preserve existing assessor gold/holdout and Week 3 labels. Adding a new
  source changes invoice questions' answerability; historical missing-evidence
  results are not comparable against an expanded corpus without matching
  source/version scope.
- No unsafe automatic candidate; every such candidate must pass the semantic
  rubric. Report false rejects and positive eligibility coverage too:
  reviewing everything is safe but does not complete the automation goal.
- Preserve the Week 4 quality/latency targets and bounded tuning budget. A
  miss leads to review-first/no-go unless the learner approves a documented
  change, not more untracked tuning or relabeled gold.

## Alternatives and tradeoffs

1. **Wait for a perfect assessor:** rejected. Small status agreement is not
   a correctness certificate and delays a useful product slice indefinitely.
2. **Authorize on `sufficient`, quotes, or heuristic confidence:** rejected.
   These cannot prove request coverage, applicable conditions, or final-text
   truth.
3. **Keep all generated replies permanently manual:** useful as a temporary
   development boundary, but does not demonstrate the automation objective.
4. **Scoped FAQ eligibility plus independent end-to-end evaluation:** chosen.
   More interpretable boundaries and lower consequences, at the cost of a
   deliberately small supported workload and conservative false rejects.

The approved synthetic facts, including navigation and role rules, are
invented teaching fixtures, not production policies. Small-sample success
cannot establish production error rates or authenticated tenant isolation.

## Rollback and validation

Disable pilot automation to restore review-first handling for new generated
requests; disable generation to restore default preview/manual handling.
Test both transitions and saved-state gates before promotion. Rollback does
not rewrite historical replies or assessment-feedback events.

## Week 4 Day 2: generated request flow

The learner approved **two sequential local model calls** for this pilot:

1. Retrieve the real pgvector passages and run the existing structured
   evidence assessor once. Validate its schema, retrieved chunk IDs, and exact
   quotes; derive status/action in application code. This is composed directly
   into the draft request and does not require a reviewer to call the separate
   saved-trace assessment/feedback APIs.
2. For `sufficient` or `partial` findings, give the response model only the
   validated answers, directly supported facts, quote/provenance context, and
   explicit undetermined parts. Do not give it raw, unassessed nearest
   passages as permission to assert facts.
3. For no hits, clarification, no relevant evidence, insufficient evidence,
   or conflicts, do not call the response generator; return an explicit,
   review-required abstention/clarification.

Both models default to `qwen3:4b` through independent settings. Response
generation is deterministic (`temperature=0`) with a 256-token output budget.
The final response call is constrained to a JSON schema with a single `draft`
field and its parsed value is validated before use; a nonblank, concise
customer-facing message is requested. This addresses an observed Qwen behavior:
unstructured output repeated the task instructions until it hit the token cap.
An incomplete, capped, malformed, invalid-quote, or failed model result is an
explicit HTTP error, never a successful-looking fallback. The assessor prompt
requires every quote to be one contiguous exact source span; its validator was
not weakened after an initial smoke request exposed a quote that skipped an
intervening sentence. No confidence is fabricated. Every result from this path
remains `pending_review`, and the default feature flag is off.

Persist the canonical response, validated assessment, source/chunk citations,
model tags, prompt/schema hashes, per-call metrics, elapsed times, output
budget, and completion verification. Prompt hashes avoid storing raw prompts,
which contain the customer question; a mutable tag plus hash is not immutable
model provenance or full reproducibility. At the Day 2 baseline, this path did
not implement automatic eligibility or change the human-review/simulated-
delivery gates.

Day 1 validation was offline: source request schemas, existing section
chunking/quote containment, JSONL integrity, fact/source references, split
coverage, route consistency, and pinned fingerprints. Day 2 indexed the
approved source and verified an API smoke request separately from held-out
evaluation; the smoke result is recorded below.

### Day 2 smoke evidence (2026-10-14)

Indexed `billing-invoice-faq-01` / `week4-synthetic-v1` through the existing
ingestion path (four chunks; `qwen3-embedding:0.6b`, 1024 dimensions). One
approved invoice-download development question completed through the API with
three citations and sufficient evidence. The persisted trace
`cb339370-f807-4d96-afe5-c0f57fe37efd` has `draft_mode=generated`,
`review_status=pending_review`, `requires_human_review=true`, null confidence,
and verified generation completion. The customer-facing response covered the
download steps, authorized roles/workspace condition, and copilot boundary.

For this single sample, API total time was 7.392s; assessor time was 6.123s
(529 output tokens), generator time 1.115s (66 output tokens), and client wall
time 7.438s. These numbers are a smoke observation, not a latency benchmark or
quality result. No held-out cases ran, and no automatic handling or external
delivery was enabled.

The assessor also proposed an unrelated invoice-number fact. The response
generator did not use it, but the current citation set still included its
source. The smoke therefore does not establish citation precision; semantic
attribution/relevance remains a W4-04 evaluation item.

## Week 4 Day 3: final-response checks and risk routing

The generated path now records deterministic checks over the final response
and its evidence: response length/sentence bounds, recognized FAQ family and
request topics, low-risk routing, sufficient assessment, exact quote
provenance, approved source/version/date/scope/content checksum, matching
evidence sections, required FAQ conditions, prohibited action claims, and
internal identifiers. The candidate decision and blocking reason codes are
persisted with the generation metadata. A default-low-risk route or a
`sufficient` assessment alone cannot pass this policy.

These are conservative, contract-specific string and provenance guards. They
do **not** establish semantic entailment between every final claim and its
citations, citation relevance, or complete meaning/coverage; those require the
independent same-response review in W4-04. The saved
`semantic_review_status=not_performed` makes that limitation explicit.

`SUPPORT_DRAFT_AUTOMATION_ENABLED` defaults to `false` and is invalid unless
`SUPPORT_DRAFT_GENERATION_ENABLED` is also true. Keep it disabled until the
W4-04 promotion gates pass and explicit approval is given. Only a generated,
persisted candidate with both automation enabled and a positive eligibility
record can use `not_required` simulated delivery. Pending, rejected,
preview-only, disabled, and ineligible paths remain blocked; human-approved or
human-edited delivery is unchanged. No real messages are sent.

Focused regression coverage exercises eligible invoice-copy and invoice-field
candidates, out-of-scope requests, unapproved source content/sections, missing
conditions, prohibited action claims, internal identifiers, high-risk and
default-low-risk fallbacks, and persisted delivery authorization. This
coverage verifies implementation behavior, not semantic response quality or
promotion readiness.
