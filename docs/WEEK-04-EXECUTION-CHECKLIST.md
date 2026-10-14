# Week 4 Execution Checklist: Grounded Responses and Bounded Automation

Date: 2026-10-14
Status: W4-01 and W4-02 complete; W4-03 through W4-05 pending. Generated replies remain opt-in and review-first; automation is not enabled.
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
- [ADR-012](./adr/012-scoped-faq-pilot-and-automation-eligibility.md) records the approved scoped eligibility policy: initial review-first generation; no-review only after validated whole-request support, final-response checks, promotion gates, and explicit enablement. Implementation remains pending.

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
| W4-03 | Final-response checks and risk routing | Pending | W4-01, W4-02 |
| W4-04 | End-to-end evaluation | Pending | W4-02, W4-03 |
| W4-05 | Bounded automation rollout and timing | Pending | W4-04 |

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
was returned. W4-03/W4-04 must evaluate final-response attribution and
irrelevant citations.

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

- [ ] W4-03a: Validate the final response, not just the assessor proposal: provenance/attribution, permitted facts, required conditions, request coverage, and prohibited promises/actions. Document which checks are deterministic and which still require semantic evaluation.
- [ ] W4-03b: Implement the approved eligibility policy: only explicitly covered low-risk FAQs passing the final checks may become `not_required` after promotion. High-risk, unknown/out-of-pilot, ambiguous, conflicting, partial, and failed cases remain review/clarification/abstention paths.
- [ ] W4-03c: Add per-case routing reasons and tests proving that a correct quote, `sufficient`, or the router's default low-risk fallback cannot alone bypass review. Do not fake confidence to satisfy the legacy numerical gate.
- [ ] W4-03d: Verify saved review/delivery state follows the decision: pending/rejected/preview-only cannot be simulated as delivered; eligible generated replies can follow the existing `not_required` path. Feedback never changes authorization.

Exit evidence: a tested eligibility/route matrix and persistence/API regressions,
with automatic handling still gated until W4-04 passes.

## Day 4: End-to-end evaluation

ID: **W4-04**
Learning focus: evaluate the same final response, not disconnected components.

- [ ] W4-04a: Extend/reuse existing evaluation helpers to capture one API outcome per case with trace, mode, intent/risk, nullable confidence, review triggers, model, citations, generation completion/error, and latency. Keep raw reply text in local quality artifacts, not operational metrics.
- [ ] W4-04b: Score that same response for retrieval, citation attribution, semantic correctness, omitted requests/conditions, prohibited claims, and final route. Explain review counts per case; the old 20/20 baseline lacks enough telemetry to retroactively prove its individual causes.
- [ ] W4-04c: Run development cases with a bounded change budget, then one untouched held-out run of the final candidate. Distinguish automation eligibility from actual handling while the pilot is review-first. Report automated, reviewed, clarified/abstained, and failed counts separately, with denominators and manual-review coverage.
- [ ] W4-04d: Evaluate the promotion gates below and record a go/no-go decision. Do not present phrase matching, citation IDs, or aggregate assessor agreement as semantic proof.

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

## Day 5: Bounded automation rollout and timing

ID: **W4-05**
Learning focus: measured automation value and latency, not a forced review quota.

- [ ] W4-05a: Capture one first-request cold/load profile and a bounded sequential warm run of at least 20 requests across approved development cases. Record sample count, model/prompt/output budget, hardware/power state, token counts, component times, client wall time, p50/p95, routing, and quality.
- [ ] W4-05b: Compare with default-path targets p50 <= 4s / p95 <= 8s. Report warm and combined percentiles, the cold request separately, and the observed cold/warm mix; this is a local experiment, not a load test or an SLO-compliance claim. Any target miss blocks promotion unless the learner explicitly approves a documented target/scope change.
- [ ] W4-05c: If all promotion gates pass, explicitly enable only the approved low-risk automatic pilot and test an eligible FAQ plus high-risk, unsupported, and flag-off controls. Otherwise keep real generated replies review-first and record the blocker and one bounded next decision. Verify rollback restores preview/manual handling.

Exit evidence: real grounded responses with demonstrated conditional no-review
handling, or an explicitly blocked automation goal with working review-first
generation. Do not call automation complete in the no-go outcome. Delivery
remains the local hash-only simulation; no real messages are sent.

## Progress evidence

| Date | Task | Evidence/result |
|---|---|---|
| 2026-10-14 | W4-01a | Inspected current code, all three source fixtures, the 12-case Week 3 contract, existing evaluators, and committed checkpoint `5a50e1a`. No new model/evaluation run. |
| 2026-10-14 | W4-01b | Learner selected the narrow low-risk FAQ scope. Exact FAQ facts, sources, and eligibility policy remain W4-01c work. |
| 2026-10-14 | W4-01c | Learner approved two FAQ families, synthetic facts/public demo scope, Qwen3:4b baseline, and scoped eligibility with null confidence. ADR-012 qualifies ADR-008/011's future gate; current preview behavior is unchanged. |
| 2026-10-14 | W4-01d (prepared) | Selected API venv `python -` offline check using `IngestionPreviewPipeline.preview` and Pydantic: source valid; 4 chunks; all 8 fact quotes retained; 8 development + 8 held-out cases valid with split coverage and consistent routes. Fingerprints recorded; learner case/rubric approval and freezing pending. No database/model calls. |
| 2026-10-14 | W4-01d (complete) | Learner reviewed the contract summary and explicitly approved freezing cases/rubric after the guided walkthrough. Manifest, source/case hashes, 6 rubric dimensions, and 47 local documentation links verified; `git diff --check` passed. Full readings remain unchecked. At this freeze point there had been no indexing or inference; changes remain unstaged and uncommitted. |
| 2026-10-14 | W4-02 (first smoke failures) | The first assessor result spliced non-adjacent source text into one quote; exact-substring validation correctly rejected it (HTTP 502). After strengthening the contiguous-quote instruction without weakening validation, the second request reached generation but its unstructured answer echoed the task and hit the 256-token cap (HTTP 502). |
| 2026-10-14 | W4-02 (complete) | Switched the final response to a strict `{"draft": ...}` schema and concise customer-facing instructions, retaining the 256-token cap. The approved development question returned HTTP 200; the complete answer was supported by indexed FAQ evidence, cited, and persisted `pending_review` with null confidence. Trace `cb339370-f807-4d96-afe5-c0f57fe37efd`; API total 7.392s, assessor 6.123s/529 output tokens, generator 1.115s/66 output tokens, client wall 7.438s. One smoke sample only; no held-out run or citation-precision claim. The assessor proposed an unrelated invoice-number fact that was not used in the reply, but its citation was returned; final attribution/relevance is a W4-03/W4-04 item. API suite: 155 tests passed; compileall, diagnostics, and `git diff --check` passed. |

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
