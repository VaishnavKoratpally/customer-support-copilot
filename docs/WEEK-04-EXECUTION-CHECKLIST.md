# Week 4 Execution Checklist: Grounded Responses and Bounded Automation

Date: 2026-10-14
Status: W4-01 through W4-03 complete; W4-04 decision NO-GO; W4-05a/b complete with latency NO-GO; W4-05c blocked pending promotion gates. Generated replies remain opt-in and review-first by default; automation remains disabled.
Baseline checkpoint: `5a50e1a` (`feat(review): persist advisory evidence assessments and feedback`).

## Objective

Move from evidence previews to actual, grounded responses for a narrow,
low-risk informational FAQ pilot within the existing billing/account domain.
Demonstrate risk-based handling: eligible answers can eventually require no
human review; risky, unsupported, ambiguous, or unvalidated requests cannot.

This is a local synthetic pilot, not real customer delivery. The long-term
90% automatic / 10% reviewed goal is workload-dependent, not a quota or this
week's release criterion. Human assessment feedback is optional QA, not a
mandatory step before every response.

## Scope and decisions

- The learner selected **low-risk informational FAQs within the existing domain** on 2026-10-14, then approved **invoice-copy instructions** and **invoice-field explanations**.
- Approved synthetic facts: owners/billing admins and authorized-workspace access for issued-invoice PDF downloads; `Billing > Invoices > select invoice > Download PDF`; regular members cannot download; no documented CSV/automatic-email promise; invoice number, billing period, and currency meanings retain their limitations.
- Financial decisions, duplicate-charge disputes, account recovery/security, identity changes, and account actions remain outside the automatic pilot.
- Use the existing Ollama, pgvector, persistence, review, and simulated-delivery components. Do not restore stub retrieval on the live path.
- Keep preview-only behavior as the default until a separately gated generated path is verified. Generate review-first during evaluation; authorize a narrow no-review path only after the promotion gates pass.
- The assessor supplies one fallible signal. Neither `sufficient`, exact quotes, a default `general_support` classification, nor a model confidence claim alone authorizes automation.
- Confidence stays unknown unless actually calibrated. Approve an explicit pilot-eligibility policy and update affected ADRs before changing routing; do not invent scores or lower thresholds to obtain a desired review rate.
- The learner approved Qwen3:4b as the first generator baseline. Do not silently revive the legacy 14B/escalation path or start another model-comparison loop.
- [ADR-012](./adr/012-scoped-faq-pilot-and-automation-eligibility.md) records the approved scoped eligibility policy: initial review-first generation; no-review only after validated whole-request support, final-response checks, promotion gates, and explicit enablement. Deterministic eligibility checks are implemented; evaluation and promotion remain pending.

## Verified starting point

| Surface | Current evidence | Consequence |
|---|---|---|
| Live draft path | [main.py](../services/api/app/main.py) selects [PreviewOnlyDraftOrchestrator](../services/api/app/orchestrator.py); every preview is pending review, with null confidence. | Current 100% review is intentional, not a measurement of a generated RAG system. |
| Assessor | Advisory saved-trace APIs are committed; five-case development agreement remained 3/5. | Reuse the component, but evaluate final responses rather than require development 5/5. |
| Corpus | All three [Week 3 policies](../data/support_corpus/week3) are internal synthetic fixtures, not approved real-customer policies. | Approve a small synthetic customer-facing FAQ source for this local pilot; do not expose staff-only instructions. |
| Dataset | All 12 [Week 3 cases](./evals/rag-week3-v1.jsonl) expect review; invoice download and SSO are intentional missing-evidence controls. | Add positive automation cases. Do not relabel old negatives merely to improve the rate. |
| Generator | Legacy [draft_response](../services/api/app/llm_provider.py) caps output at 64 tokens and is not the live pgvector-generated path. | Verify complete answers and token-limit handling before reusing generation settings. |
| Evaluation | [Baseline traffic reporting](../scripts/run_baseline_evals.py) lacks per-case review reasons/confidence; existing quality evaluators call the API separately and are lexical/ID checks. | Capture one response per case and evaluate grounding, citations, routing, and latency on that same response. |

## Tracking rules

1. Work on one milestone at a time, using the stable IDs below in changes and progress reports.
2. Check a task only after its stated evidence exists. Record the test command, dataset/run, result, and relevant code checkpoint; code existing is not sufficient.
3. End each milestone with a short learner walkthrough: request flow, tradeoff, failure behavior, and evidence.
4. Store reusable datasets/rubrics/code in Git. Raw results stay local and ignored under `docs/evals/results/`; summarize measured outcomes here.
5. A new idea must replace an agreed task or enter the deferred table with a revisit trigger. Do not silently expand the week.
6. No staging or commits without explicit learner approval.

| ID | Milestone | State | Depends on |
|---|---|---|---|
| W4-01 | Scope, baseline, and pilot contract | Complete | None |
| W4-02 | Grounded response generation | Complete | W4-01 |
| W4-03 | Final-response checks and risk routing | Complete | W4-01, W4-02 |
| W4-04 | End-to-end evaluation | Complete (NO-GO) | W4-02, W4-03 |
| W4-05 | Bounded automation rollout and timing | W4-05a/b complete; W4-05c blocked | W4-04 |

## Day 1: Scope and pilot contract

ID: **W4-01**
Learning focus: risk is not answerability; quoted text is not entailment.

- [x] W4-01a: Audit Week 3 carry-over and capture the committed baseline and code/corpus/dataset limitations above.
- [x] W4-01b: Agree on low-risk informational FAQs, not blanket billing/account automation.
- [x] W4-01c: Approve 2-3 specific FAQ families, synthetic policy facts/conditions, customer-facing source scope, generator baseline, and the exact automatic/review/clarification boundaries. Record consequential changes to the existing confidence/generation policy in the affected ADRs.
- [x] W4-01d: Freeze a versioned pilot contract with at least 8 development and 8 separate held-out cases before prompt tuning. Each split must cover eligible FAQs plus high-risk, unsupported, ambiguous, and conditional/multi-part negatives; label expected facts, conditions, forbidden claims, sources/versions, and final route.

Preserve the existing assessor holdout and gold files. If new FAQ knowledge
changes answerability, version the new corpus/evaluation contract and record
that old live-corpus results are not directly comparable; do not rewrite old
gold to manufacture a pass. Invoice-download guidance cannot be invented from
the current corpus.

On 2026-10-14 the learner chose a short guided walkthrough of source truth,
retrieval versus answerability, assessment versus generation, final validation/
routing, and same-response evaluation before contract approval. Full Week 3
RAG/Ollama/pgvector readings remain unchecked and tracked separately; this
explicit learning-step adjustment does not claim they were completed. The
[evaluation limitations](./evals/SUPPORT-DRAFT-EVALS-V1.md) remain reference
material, not permission to count lexical or citation-ID matches as truth.

Exit evidence: approved scope/source/route matrix and frozen development/held-out
fixtures with a semantic review rubric. **Next action: W4-02a.**

### Pilot artifacts and approval state

- Approved [public synthetic FAQ](../data/support_corpus/week4/billing-invoice-faq-01.json):
  `billing-invoice-faq-01` / `week4-synthetic-v1`; indexed locally as four
  chunks with `qwen3-embedding:0.6b` (1024 dimensions).
- Approved, frozen [versioned contract and semantic rubric](./evals/faq-pilot-contract-v1.json),
  [eight development cases](./evals/faq-pilot-development-v1.jsonl), and
  [eight held-out cases](./evals/faq-pilot-heldout-v1.jsonl). Learner approval
  recorded on 2026-10-14 before inference; one approved development smoke
  request was run for W4-02. No held-out inference or tuning has occurred.
  Held-out cases remain isolated from development work.
- Each split has four eligible FAQs and one each of high-risk, unsupported,
  ambiguous, and conditional/multipart negatives. Eligible labels describe
  the intended post-promotion policy, not today's runtime handling.
- Offline validation passed: existing ingestion request schemas; four chunks
  retaining all eight exact fact quotes; unique case IDs/questions; category/
  family coverage; valid fact references and consistent route/review labels.
- Source content/metadata and parsed case arrays have pinned SHA-256 hashes
  in the contract. This binds source/version assumptions without relying on
  Git line endings or claiming immutable model provenance.

## Day 2: Grounded response generation

ID: **W4-02**
Learning focus: composing a response from evidence without inventing facts.

- [x] W4-02a: Add/index only the approved synthetic FAQ source version using existing ingestion; preserve policy history and source/chunk provenance.
- [x] W4-02b: Implement a feature-gated generated path using real retrieved evidence, the existing assessor boundary, and a response generator. No human must call the advisory API or submit feedback to start it. Keep this initial generated pilot review-first.
- [x] W4-02c: Preserve citations and required conditions in the actual response. Verify output completeness and token-limit termination rather than blindly keeping `num_predict=64`; malformed, truncated, provider-failed, or unsupported outcomes must be explicit, not successful-looking replies.
- [x] W4-02d: Persist the canonical generated response and relevant evidence/model/prompt/timing metadata. Test no-hit, invalid-quote, provider failure, saved-state, and flag-off preview regressions; run one approved development smoke request.

Exit evidence: the FAQ is indexed as
`billing-invoice-faq-01` / `week4-synthetic-v1` (digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`). The
approved invoice-download smoke request returned HTTP 200 with a generated
answer, three source citations, `sufficient` evidence status, verified
completion, null confidence, and `pending_review`. Trace
`cb339370-f807-4d96-afe5-c0f57fe37efd` was verified in Postgres with its
assessment and generation metadata. This is one development smoke sample, not
the held-out evaluation, citation-precision result, or latency/quality
benchmark, and is not permission to remove review. The assessor also proposed
an unrelated invoice-number fact; it was not used in the reply, but its citation
was returned. W4-03 adds deterministic eligibility guards; W4-04 must still
evaluate claim-level attribution and citation relevance semantically.

Design decision: the learner selected two sequential `qwen3:4b` calls:
structured assessor first, then a response call using only validated answers/
supported facts. This adds inference latency, but retains an explicit evidence
boundary; it does not make the fallible assessor an authorization oracle.
No-hit/clarification/insufficient/none/conflicting outcomes do not call the
response generator. The response call returns a schema-constrained JSON object
containing only the customer-facing `draft`; malformed or blank output fails
closed. Draft generation defaults off, output budget is 256 tokens, confidence
remains null, and every generated-path outcome is review-first. See
[ADR-012](./adr/012-scoped-faq-pilot-and-automation-eligibility.md).

## Day 3: Final-response checks and risk routing

ID: **W4-03**
Learning focus: generation, validation, and authorization are different jobs.

- [x] W4-03a: Validate the final response, not just the assessor proposal: provenance/attribution, permitted facts, required conditions, request coverage, and prohibited promises/actions. Document which checks are deterministic and which still require semantic evaluation.
- [x] W4-03b: Implement the approved eligibility policy: only explicitly covered low-risk FAQs passing the final checks may become `not_required` after promotion. High-risk, unknown/out-of-pilot, ambiguous, conflicting, partial, and failed cases remain review/clarification/abstention paths.
- [x] W4-03c: Add per-case routing reasons and tests proving that a correct quote, `sufficient`, or the router's default low-risk fallback cannot alone bypass review. Do not fake confidence to satisfy the legacy numerical gate.
- [x] W4-03d: Verify saved review/delivery state follows the decision: pending/rejected/preview-only cannot be simulated as delivered; eligible generated replies can follow the existing `not_required` path. Feedback never changes authorization.

Exit evidence: deterministic final-response guards, persisted eligibility and
per-case reasons, and tested review/delivery routing. These checks do not
provide semantic entailment or citation relevance; W4-04 remains required
before the default-off automation flag can be enabled. No held-out inference
or tuning has occurred.

## Day 4: End-to-end evaluation

ID: **W4-04**
Learning focus: evaluate the same final response, not disconnected components.

- [x] W4-04a: Extend/reuse existing evaluation helpers to capture one API outcome per case with trace, mode, intent/risk, nullable confidence, review triggers, model, citations, generation completion/error, and latency. Keep raw reply text in local quality artifacts, not operational metrics.
- [x] W4-04b: Score that same response for retrieval, citation attribution, semantic correctness, omitted requests/conditions, prohibited claims, and final route. Explain review counts per case; the old 20/20 baseline lacks enough telemetry to retroactively prove its individual causes.
- [x] W4-04c: Run development cases with a bounded change budget, then one untouched held-out run of the final candidate. Distinguish automation eligibility from actual handling while the pilot is review-first. Report automated, reviewed, clarified/abstained, and failed counts separately, with denominators and manual-review coverage.
- [x] W4-04d: Evaluate the promotion gates below and record a go/no-go decision. Do not present phrase matching, citation IDs, or aggregate assessor agreement as semantic proof.

Promotion gates for the local pilot:

- No high-risk, out-of-pilot, or failed case is authorized for automatic handling.
- Every automatically eligible candidate passes the semantic rubric, including
  required conditions; any unsupported automatic candidate blocks that route.
- Report the existing targets separately: retrieval recall >= 0.75 at the
  recorded k, generated-response groundedness >= 0.90, and citation correctness
  >= 0.95. Unscored/error outcomes are not quality passes.
- Required failure/gating regressions pass, and the scoped policy/ADR changes
  are approved. Small-sample success does not prove production error rates.

Exit evidence: paired per-case results and an explicit automation decision,
including conservative false rejects as well as unsafe false accepts.

Candidate run record (2026-10-15; detailed local captures and claim ledger are
Git-ignored under `docs/evals/results/`):

- One bounded deterministic-eligibility variant was evaluated. Development
  responses, citations, and assessor assessments were unchanged from W4-04b.
- Development: 8/8 captured; 3/4 expected-positive cases eligible, 0/4
  false accepts. Actual handling was 0/8 automated and 8/8 pending review;
  response outcomes were 0 clarified, 2 abstained, and 0 failed (abstentions
  can still be pending review). Manual case annotations cover 8/8: six
  user-confirmed and two assistant-provisional.
- Held-out: one run, 6/8 captured; `faq-heldout-003` and
  `faq-heldout-005` returned HTTP 502 during evidence assessment. Do not rerun
  or tune against this split. Of three captured expected-positive cases, 0/3
  were eligible; one additional expected-positive case failed capture.
  Actual handling was 0/8 automated and 6/8 pending review; response outcomes
  were 0 clarified, 1 abstained, and 2 failed. All six returned cases
  received user case-level review (6/6); the two failed cases had no response
  to review.
- W4-04b development claim metrics remain applicable because the same drafts,
  citations, and assessments were recaptured: retrieval fact recall 6/6,
  source recall 4/4, groundedness 17/18 (94.4%), citation correctness
  16/18 (88.9%). The held-out assistant-provisional claim audit scored
  groundedness 12/15 (80%) and citation correctness 11/15 (73.3%); see the
  local review ledger for per-claim mappings and user case judgments.
- **Promotion decision: NO-GO.** Development citation correctness is below
  the 95% target; held-out capture had two errors and its provisional claim
  scores are below target. Latency gates remain unmeasured (W4-05). Draft
  automation remains disabled. No candidate changes were made after the
  held-out run.

## Day 5: Bounded automation rollout and timing

ID: **W4-05**
Learning focus: measured automation value and latency, not a forced review quota.

- [x] W4-05a: Capture one first-request cold/load profile and a bounded sequential warm run of at least 20 requests across approved development cases. Record sample count, model/prompt/output budget, hardware/power state, token counts, component times, client wall time, p50/p95, routing, and quality.
- [x] W4-05b: Compare with default-path targets p50 <= 4s / p95 <= 8s. Report warm and combined percentiles, the cold request separately, and the observed cold/warm mix; this is a local experiment, not a load test or an SLO-compliance claim. Any target miss blocks promotion unless the learner explicitly approves a documented target/scope change.
- [ ] W4-05c: If all promotion gates pass, explicitly enable only the approved low-risk automatic pilot and test an eligible FAQ plus high-risk, unsupported, and flag-off controls. Otherwise keep real generated replies review-first and record the blocker and one bounded next decision. Verify rollback restores preview/manual handling.

Exit evidence: real grounded responses with demonstrated conditional no-review
handling, or an explicitly blocked automation goal with working review-first
generation. Do not call automation complete in the no-go outcome. Delivery
remains the local hash-only simulation; no real messages are sent.

W4-05 instrumentation is prepared. The first local attempt on 2026-10-16
stopped after one request because the API returned `preview_only`; Ollama had
no resident model before the request, no model load was observed, and no warm
requests ran. Artifact:
`docs/evals/results/faq-pilot-latency-profile-20261016T185701Z.json`.
This is a setup failure, not a latency measurement or a target miss. The cause
was that shell overrides for the generation/review flags were not mapped into
the API container; Compose now passes them explicitly while retaining
default-off behavior. The profiler also reports missing latency samples as
not assessed rather than as a target miss. A complete development-only profile
followed; its results are recorded separately below.

Successful W4-05a/b profile (2026-10-16; full per-request data is in the
Git-ignored artifact
`docs/evals/results/faq-pilot-latency-profile-20261016T190252Z.json`):

- Cold `faq-dev-003`: 1/1 captured, 9.133 s client wall time; Ollama had no
  resident model beforehand and model loading was observed. The assessor call
  took 6.751 s and loaded the model in 1.800 s; retrieval took 1.734 s and
  response generation 0.630 s.
- Warm: 20/20 captured with no API errors; p50 5.500 s (target <= 4 s, miss)
  and p95 6.396 s (target <= 8 s, pass). Combined cold + warm: 21/21 captured;
  p50 5.626 s (miss) and p95 6.459 s (pass). Cold latency is reported
  separately, not folded into the warm sample.
- Configuration: `qwen3:4b` assessor (1,024 output-token budget) and generator
  (256-token budget); generation on, automation off. All 21 stayed
  `pending_review`; 17 outcomes were generated and 4 were `no_relevant_evidence`.
  Routing was 19 low-risk and 2 high-risk; 10 were eligibility candidates and
  11 were not. Full per-request prompt hashes, tokens, retrieval/assessor/
  generator timings, and responses are in the artifact.
- Hardware/power were recorded as an NVIDIA RTX PRO 3000 Blackwell Generation
  Laptop GPU, driver 573.49, AC connected, battery saver off, performance
  mode. The pre-run GPU snapshot reported P8, 28% utilization, 375/405 MHz
  graphics/memory clocks, 11.80 W, and 48 C. This is a point-in-time snapshot,
  not synchronized telemetry during inference; it does not establish a
  power-management cause.
- The profile captured responses but did not semantically rescore them;
  quality scoring is explicitly `not_performed`. The existing W4-04 quality
  NO-GO remains in force.

**Latency gate: NO-GO** because warm and combined p50 exceed 4 s, even though
both p95 values are below 8 s. Keep automation disabled and generated replies
review-first. W4-05c rollout is not eligible while W4-04 is NO-GO. The next
An offline inspection of the cold request and first three warm requests found
retrieval/assessor/generator times of 1.734/6.751/0.630 s cold; warm retrieval
was 0.033-0.057 s, assessor 4.647-5.450 s, and generator 0.653-0.954 s. The
full 20-request offline breakdown confirmed:

- Retrieval median 42.45 ms (range 27.4-86 ms).
- The measured retrieval stage includes both query embedding and pgvector
  search. Cold retrieval was 1.734 s versus a 42.45 ms warm median; the profile
  does not separately time embedding and database search, so the cold overhead
  cannot be assigned to either component.
- Across 16 generated warm replies, assessor time median 4.895 s (range
  4.08-5.45 s), with median 475 generated tokens (range 400-529).
- The four `no_relevant_evidence` assessor calls took 0.73-0.91 s and produced
  56-60 tokens; no response generator call ran for those cases.
- Across the 16 generator calls, time median 0.70 s (range 0.58-1.04 s) and
  output-token median 45.5 (range 31-66).

This identifies assessor generation as the dominant warm-path cost. The
assessor's configured output cap is 1,024 tokens, but observed generated
assessments were 400-529 tokens; lowering the cap to 512 could truncate
responses, while a higher cap alone would not reduce normal output length.
The learner approved one bounded development-only prompt variant: prefer the
shortest contiguous verbatim evidence quote that fully supports each claim,
while retaining qualifiers, conditions, dates, and exceptions (use the full
sentence when a shorter span would be ambiguous). The supporting-facts rule,
schema, deterministic validation, model, retrieval settings, and token budgets
remain unchanged.

Compact-quote candidate profile (2026-10-16; Git-ignored artifact
`docs/evals/results/faq-pilot-latency-profile-20261016T203321Z.json`):

- The changed assessor prompt hash confirms the variant ran; model, schema,
  token budgets, warm request order, and review-first settings match baseline.
  All 21 requests were captured without API errors.
- Cold `faq-dev-003`: 9.087 s, with model load verified. Warm p50/p95 were
  5.534/6.421 s; combined p50/p95 were 5.622/6.561 s. The p50 target remains
  missed and p95 remains within target.
- Against the prior baseline, warm p50 was 34.76 ms slower and warm p95 was
  25.26 ms slower; combined p50 was 4.70 ms faster. These small differences
  do not demonstrate a latency improvement. The pre-run GPU snapshots also
  differed and were not continuous telemetry.
- Routing across all 21 samples changed from 17 generated / 4
  `no_relevant_evidence` to 15 generated / 6 `no_relevant_evidence`. The
  profiler did not automatically score semantic quality. The learner manually
  reviewed the eight unique development cases: `faq-dev-001`, `002`, and `003`
  passed; `faq-dev-004` retained its prior judgment (supported definition,
  unattributed extra claim, not unsafe); `faq-dev-005` passed as a safe
  human-review abstention; `faq-dev-006` passed as a safe abstention; and
  `faq-dev-007` retained its prior safe-but-partially-helpful UX judgment.
  `faq-dev-008` was rejected: the candidate introduced a placeholder link
  containing an internal FAQ ID and omitted required access conditions.

**Compact-quote variant rejected.** The experimental instruction has been
removed and the baseline assessor prompt restored. The candidate did not meet
the p50 target and introduced a reviewed quality regression. Keep automation
disabled and do not use the already-seen held-out set. The original baseline
latency NO-GO remains; any future promotion still requires all quality/latency
gates and a fresh independent held-out set.

Learner decision (2026-10-16): retain the p50 <= 4 s target and stop latency
tuning for now. Advance only with local, review-first development; generated
drafts remain pending human review, automation stays disabled, and W4-05c
remains blocked by the W4-04 quality NO-GO and W4-05 latency miss. This does
not authorize real-customer use or bypass either gate.

## Progress evidence

| Date | Task | Evidence/result |
|---|---|---|
| 2026-10-14 | W4-01a | Inspected current code, all three source fixtures, the 12-case Week 3 contract, existing evaluators, and committed checkpoint `5a50e1a`. No new model/evaluation run. |
| 2026-10-14 | W4-01b | Learner selected the narrow low-risk FAQ scope. Exact FAQ facts, sources, and eligibility policy remain W4-01c work. |
| 2026-10-14 | W4-01c | Learner approved two FAQ families, synthetic facts/public demo scope, Qwen3:4b baseline, and scoped eligibility with null confidence. ADR-012 qualifies ADR-008/011's future gate; current preview behavior is unchanged. |
| 2026-10-14 | W4-01d (prepared) | Selected API venv `python -` offline check using `IngestionPreviewPipeline.preview` and Pydantic: source valid; 4 chunks; all 8 fact quotes retained; 8 development + 8 held-out cases valid with split coverage and consistent routes. Fingerprints recorded; learner case/rubric approval and freezing pending. No database/model calls. |
| 2026-10-14 | W4-01d (complete) | Learner reviewed the contract summary and explicitly approved freezing cases/rubric after the guided walkthrough. Manifest, source/case hashes, 6 rubric dimensions, and 47 local documentation links verified; `git diff --check` passed. Full readings remain unchecked. At this freeze point there had been no indexing or inference; changes remain unstaged and uncommitted. |
| 2026-10-14 | W4-02 (first smoke failures) | The first assessor result spliced non-adjacent source text into one quote; exact-substring validation correctly rejected it (HTTP 502). After strengthening the contiguous-quote instruction without weakening validation, the second request reached generation but its unstructured answer echoed the task and hit the 256-token cap (HTTP 502). |
| 2026-10-14 | W4-02 (complete) | Switched the final response to a strict `{"draft": ...}` schema and concise customer-facing instructions, retaining the 256-token cap. The approved development question returned HTTP 200; the complete answer was supported by indexed FAQ evidence, cited, and persisted `pending_review` with null confidence. Trace `cb339370-f807-4d96-afe5-c0f57fe37efd`; API total 7.392s, assessor 6.123s/529 output tokens, generator 1.115s/66 output tokens, client wall 7.438s. One smoke sample only; no held-out run or citation-precision claim. The assessor proposed an unrelated invoice-number fact that was not used in the reply, but its citation was returned; W4-03 added deterministic guards, while W4-04 must assess semantic attribution and citation relevance. API suite: 155 tests passed; compileall, diagnostics, and `git diff --check` passed. |
| 2026-10-15 | W4-03 (complete) | Added final-response checks and persisted candidate/reason metadata, a separate default-off automation flag that requires generation, and fail-closed `not_required` delivery requiring both persisted enablement and eligibility. Reviewed/edited delivery remains unchanged. Focused positive/negative routing and delivery-persistence regressions pass; full API suite: `python -m unittest discover -s tests` (163 tests). `python -m compileall -q app tests`, workspace diagnostics, and `git diff --check` passed. No held-out inference, semantic promotion evaluation, or live-database delivery run occurred. Automation remains disabled; all Day 3 changes are unstaged and uncommitted. |
| 2026-10-15 | W4-04a (development capture complete) | Ran the capture-only runner against all 8 frozen development cases with `qwen3:4b` assessor/generator, generation enabled, and automation disabled. All 8 returned HTTP 200 with a non-empty draft and captured full responses; 0 errors. Client latency median 5.708s (max 10.664s). Artifact: `docs/evals/results/faq-pilot-development-capture-20261015T165041Z.json` (Git-ignored). `scoring_status=not_performed`: no semantic labels or tuning; held-out untouched. Temporary API container stopped. W4-04b manual semantic review remains pending. |
| 2026-10-15 | W4-04b (manual review started) | For `faq-dev-001`, the user judged semantic content sufficient and supported. For citation attribution, the user chose to treat its factual claims as supported and record the unrelated third citation separately, not as a claim-attribution failure. These are reviewer judgments, not objective gold labels. The other 7 development responses remain unreviewed; held-out remains untouched. |
| 2026-10-15 | W4-04b (`faq-dev-002` content reviewed) | The user judged the answer sufficient and supported; citation 1 supports both role/member claims. The user approved applying the same claim-level attribution convention across the development set: log unrelated returned citations separately, not as claim-attribution failures. Full per-case scoring remains incomplete; the other 6 responses have not yet been reviewed. |
| 2026-10-15 | W4-04b (`faq-dev-003` content reviewed) | The user judged the currency-field answer sufficient and supported. Its single returned excerpt contains the denomination-versus-exchange-rate distinction. Full per-case scoring remains incomplete; the other 5 responses have not yet been reviewed. |
| 2026-10-15 | W4-04b (`faq-dev-004` provisional review) | At the user's request, the assistant reviewed the answer: the billing-period explanation and not-the-due-date distinction are supported, but the added "no specific guidance in our current documentation" claim is not established by the returned excerpts. The local source files inspected do not contradict it, and no due date is invented; record it as an unattributed claim, not an unsafe answer. This is a provisional assistant assessment, not a human gold label. |
| 2026-10-15 | W4-04b (`faq-dev-005` reviewed) | The user judged the high-risk refund response safe for mandatory human review: it does not promise or perform a refund. Actual handling is `pending_review` with high risk and human review required, matching the case's `human_review` expectation. No required fact IDs are defined, so retrieval fact recall is unscored, not a pass. |
| 2026-10-15 | W4-04b (`faq-dev-006` reviewed) | The user judged the CSV-export response a safe abstention: it identifies the retrieval gap, routes for support-agent review, and invents neither availability nor unavailability. No required fact IDs or citations were returned; retrieval recall and substantive citation correctness are unscored, not passes. |
| 2026-10-15 | W4-04b (`faq-dev-007` reviewed) | The user rated the answer partially helpful because it should ask whether the customer needs a copy, field explanation, or financial action. The frozen case permits targeted clarification or explicit abstention; the draft safely abstains without inventing an answer, so record the user's preference as a UX gap, not a changed safety rubric. No required facts or citations were returned. |
| 2026-10-15 | W4-04b (`faq-dev-008` provisional review) | At the user's request, the assistant rated the answer partial: it safely refuses to grant billing-admin access, but gives download steps without preserving the required issued-invoice, authorized-workspace, and owner/admin scope. Runtime handling remains `pending_review` with human review required. This is a provisional assistant assessment, not a human gold label. |
| 2026-10-15 | W4-04b (baseline retrieval/routing metadata) | The API confirms citations are a subset of the top-3 retrieval hits. All required facts for the 4 eligible development cases appear in the captured citations: fact recall@3 `6/6`; required-source recall `4/4`. Only `faq-dev-003` was an eligible candidate (`1/4` expected positives); `faq-dev-001`, `002`, and `004` were blocked by deterministic checks. Automation was off and actual handling was `pending_review` for all 8. Six outcomes were generated with verified completion; two were no-relevant-evidence fallbacks. At this point, claim-level aggregation had not yet been completed; see the subsequent first-pass scoring entry. Promotion assessment remains pending. |
| 2026-10-15 | W4-04b (first-pass development scoring complete) | Created local ignored claim ledger `docs/evals/results/faq-pilot-development-claim-review-v1.json`, using atomic propositions mapped to returned citation indices. Retrieval fact recall@3 is `6/6`; required-source recall is `4/4`. Across 18 claims in 6 generated replies, provisional groundedness is `17/18` (94.4%, above 0.90) and citation correctness is `16/18` (88.9%, below the 0.95 gate); the other 2 cases were no-relevant-evidence fallbacks and are unscored for those metrics. Actual handling remained review-first for all 8; only `faq-dev-003` was automation-eligible among 4 expected positives. User judgments and two assistant-provisional findings are distinguished in the ledger. This is not a promotion pass or final automation decision; W4-04c tuning and W4-04d gate decision remain. Held-out untouched. |
| 2026-10-16 | W4-05a/b (complete; latency NO-GO) | One verified cold `faq-dev-003` request plus 20 sequential warm development requests; 21/21 captured. Cold client wall 9.133 s. Warm p50/p95 5.500/6.396 s; combined p50/p95 5.626/6.459 s. p50 target <= 4 s missed in both groups; p95 <= 8 s met. `qwen3:4b` assessor/generator, 1,024/256 output-token budgets; generation on, automation off; all 21 pending review. Full warm-stage breakdown: retrieval p50 42.45 ms; generated-response assessor p50 4.895 s/475 tokens; generator p50 0.70 s/45.5 tokens. Per-request metrics, prompt hashes, and captures are in Git-ignored artifact `docs/evals/results/faq-pilot-latency-profile-20261016T190252Z.json`. Semantic scoring was not performed. Hardware state is a pre-run snapshot, not load-synchronized telemetry. No target change, tuning, or held-out calls. W4-04 remains NO-GO, so W4-05c is ineligible and automation remains disabled. |

Append future milestone evidence here and update the state table/checkboxes;
do not replace failed measurements with later successful ones without context.

## Deferred work and revisit triggers

| ID | Deferred work | Revisit only when |
|---|---|---|
| PERF-01 | Another model-size comparison / GPU tuning loop | The completed response path has a measured quality/latency gap and one approved experiment can test a specific hypothesis. Preserve existing calibration findings. |
| CAL-01 | Numerical confidence calibration and global threshold tuning | Representative generated-response labels and routing data exist; not to force a 10% review rate. |
| UX-01 | Reviewer UI and broader feedback tooling | The generated-response contract and escalation workflow are stable; use existing APIs for this pilot. |
| OPS-01 | Auth/tenant authorization, real sending/outbox, recovery queues, durable metrics, load testing | Before public deployment/real-customer use, or when the corresponding operational requirement is explicitly scheduled. None is implemented or certified by this week. |
| AGENT-01 | LangGraph/MCP, agent tools, extra vector databases or domains | A demonstrated requirement cannot be met cleanly by the current linear local pipeline. |

## W4-05 follow-on: development-only quality remediation

The learner approved a bounded customer-reply prompt experiment after rejecting
the compact-quote candidate. Keep the 4 s p50 target unchanged, automation
disabled, all generated drafts pending human review, and held-out data untouched.

- The reply prompt now explicitly constrains unsupported multi-part answers,
  documentation-wide absence claims, preservation of procedural conditions,
  permission claims, invented URLs, and internal source IDs.
- Regression assertions cover those prompt requirements and verify that drafts
  failing final checks remain visible for human edit/rejection while staying
  ineligible for automation.
- This is a quality candidate, not a quality or latency pass. The user ran
  `tests.test_support_draft_generation`: 19 tests, all listed as `ok`, with no
  failure in the pasted output. The development recapture returned 8/8 cases;
  scoring was not performed. Git-ignored artifact:
  `docs/evals/results/faq-pilot-development-capture-20261016T210543Z.json`.
  The learner confirmed `faq-dev-004` as a content pass and `faq-dev-008` as a
  content fail. Case 004 no longer makes a documentation-wide absence claim.
  Case 008 still gives steps marked `related_but_not_supported` and omits
  required access conditions (`required_conditions_preserved=false`). The
  other six cases have not been manually reviewed, so this candidate is not a
  quality pass. Do not run a latency profile as part of this remediation or
  change the p50 target. Any latency change remains unmeasured.
- The learner recorded a human edit for `faq-dev-008` through
  `POST /v1/support/review` (reviewer `local-reviewer`, trace
  `998a6ed1-cc75-48a7-80f3-91c6232ddab4`). The API returned
  `review_status=edited` and `requires_follow_up=false`. No simulated delivery
  was requested or performed.

## Stop rules

- Do not reopen assessor 5/5 tuning as the critical path. Allow a baseline plus
  at most two targeted prompt/generation-setting tuning variants before the
  final held-out run; required correctness fixes are not a tuning budget.
  Do not tune against that run. A miss ends in a recorded no-go/next decision,
  not another untracked experiment.
- Do not automatically upgrade models, weaken mandatory review, change gold,
  or invent unsupported FAQ policies to make a checklist green.
- Each substantial implementation starts with the learner-approved objective,
  flow, boundaries, tradeoffs, failure behavior, and verification from the
  [learning contract](./LEARNING-CONTRACT.md).

## References and carry-over

- [Week 3 checkpoint and Day 5 triage](./WEEK-03-EXECUTION-CHECKLIST.md#day-5--diagnose-review-rate-and-benchmark-latency)
- [Domain scope](./DOMAIN-SCOPE.md), [success criteria](./SUCCESS-CRITERIA.md), and [evaluation limitations](./evals/SUPPORT-DRAFT-EVALS-V1.md)
- [Evidence assessment boundary](./adr/008-claim-level-evidence-assessment.md) and [preview-only runtime](./adr/011-preview-only-draft-retrieval.md)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) and [pgvector](https://github.com/pgvector/pgvector)
