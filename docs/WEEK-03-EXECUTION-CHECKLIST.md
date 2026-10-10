# Week 3 Execution Checklist: Evidence-Grounded RAG

## Objective

Replace the deterministic retrieval stub for a narrow support domain with a local, measurable RAG path wired into the live `POST /v1/support/draft` request path. Prove retrieval and grounding behavior before adding agent frameworks or broadening the product surface.

## Scope decisions

- Start with account recovery and billing, where the Week 2 pilot exposed evidence gaps.
- Make `/v1/support/draft` use the pgvector-backed retriever for those domains. Keep `StubRetriever` for deterministic tests, not as a fallback for user-facing requests.
- Use the same real retriever for `/v1/retrieval/query` so its inspection results match the evidence supplied to draft generation.
- Use synthetic or approved support documents; do not use real customer data.
- Reuse PostgreSQL/pgvector from the existing architecture decision; do not add Qdrant this week.
- Keep `StubRetriever` available for deterministic tests while adding the real retrieval path.
- Keep mandatory high-risk review and current confidence thresholds unchanged until the review data is understood.
- Defer LangGraph, MCP, persistent metrics infrastructure, and concurrency/load testing.

## Day 1 — Define the corpus and evaluation contract

Learning focus: what RAG must retrieve, what the generator may claim, and when the system must abstain.

- [ ] Read the introduction and architecture sections of the [RAG paper](https://arxiv.org/abs/2005.11401) and the project [support-draft evaluation guide](./evals/SUPPORT-DRAFT-EVALS-V1.md).
- [x] Select a small set of synthetic account-recovery and billing policies.
- [x] Create a fixed query set containing answerable, ambiguous, insufficient-evidence, and out-of-corpus questions.
- [x] For each case, record expected retrieval and citation source IDs, supported facts, unsupported claims to avoid, and expected review/abstention behavior.

Exit evidence: versioned source documents and a reviewed evaluation dataset are checked in before retrieval implementation.

## Day 2 — Embed and index documents

Learning focus: embeddings, chunking, vector dimensions, similarity measures, and metadata/versioning tradeoffs.

- Preserve policy history: `(source_key, policy_version)` identifies an immutable source version; changing source content or policy metadata requires a new version.
- Use exact cosine search for the small Week 3 corpus; defer approximate vector indexes until corpus size and measured latency justify them.
- [ ] Read the relevant [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) and [pgvector documentation](https://github.com/pgvector/pgvector).
- [x] Choose and record a local embedding model, its version, and vector dimension: Ollama `qwen3-embedding:0.6b` (digest `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`), 1024 dimensions confirmed by `POST /api/embed` (one-vector cold smoke test: 8.7s; not a latency benchmark).
- [x] Chunk the selected documents and preserve stable source/version/chunk IDs, checksums, effective dates, and access-scope metadata.
- [x] Store embeddings in PostgreSQL/pgvector with idempotent ingestion behavior.
- [x] Test re-ingestion, document updates, and embedding-dimension mismatch handling.

Implementation evidence: three synthetic sources produced eight stored vectors, each 1024-dimensional and tagged with the selected model digest. Identical re-ingestion was a no-op; same-version content changes were rejected; a new policy version was retained; and changing chunk configuration reindexed without changing the source-version ID. See [ADR-007](./adr/007-versioned-support-document-ingestion.md).

Exit evidence: indexed chunks can be traced to their source document and version.

## Day 3 — Implement the real retrieval path

Learning focus: query embeddings, top-k retrieval, metadata filters, and evidence sufficiency.

- [x] Implement query embedding and exact pgvector search for `/v1/retrieval/query`, returning raw cosine distances and source-version metadata.
- [ ] Wire the real retriever into `/v1/support/draft` after evidence-sufficiency and confidence/abstention behavior are defined; retain `StubRetriever` for deterministic tests, not as a user-facing fallback.
- [ ] Return citations from retrieved chunk metadata, not hard-coded source lists.
- [x] Define behavior for empty or weak evidence: ask a clarifying question, abstain, or require human review.
- [ ] Add endpoint-level tests proving `/v1/support/draft` receives real retrieved chunks and citations, plus tests for filtering and no-evidence behavior. Out-of-scope requests must not silently fall back to static stub evidence.

Implementation evidence for the first retrieval slice: `/v1/retrieval/query` now embeds each question and performs exact cosine search over the latest effective `public` and `internal` policy versions. It returns the raw distance and source/chunk metadata; it does not return a confidence score or decide evidence sufficiency. Ambiguous same-date versions and model/digest mismatches fail explicitly. `/v1/support/draft` remains on `StubRetriever` until its evidence and confidence behavior is designed.

Design evidence for evidence sufficiency is captured in [ADR-008](./adr/008-claim-level-evidence-assessment.md). The contract records the fact or value requested separately from an optional evidence-backed answer and from other directly relevant, supported response facts. This represents questions such as "How long?" without forcing the question into a claim or inventing a missing value. It validates exact quotes and retrieved chunk IDs, then maps findings to deterministic statuses and actions. For `bi-005`, the credit-posting date is requested but unanswered, while the initial review window and no-guarantee rule are separately supported facts; together they justify `partial`.

The standalone local assessor requests schema-constrained output from Ollama and validates it against the typed proposal and retrieved chunks. Unit tests cover aggregation, parsing, provider failures, duplicates, and quote validation. Initial real-model checks have not passed: Qwen3:4b returned schema-valid but incorrect assessments, including `none` despite relevant evidence and, in an experimental prompt variant, a duplicate claim with an unsupported quote-to-claim relationship. Requests with Qwen3:4b thinking enabled, Qwen3:14b, and the revised separated-claim schema exceeded 180-second, 240-second, and 180-second client timeouts, respectively. These are failure observations, not a benchmark. Do not wire the assessor into `/v1/support/draft` until labeled evaluation demonstrates acceptable claim coverage and no false-sufficient decisions.

### Deferred: live draft-path integration

As of 2026-10-10, keep `/v1/support/draft` on `StubRetriever`. This is an
explicit deferral, not a completed Day 3 objective. Do not spend more time
trying to make Qwen3:4b perfect; keep the assessor standalone while continuing
Day 4 evaluation.

Revisit the three unchecked Day 3 items after measuring retrieval and draft
behavior and defining a human-review gate enforced by the API/client. Until
retrieval confidence is calibrated, represent it as unknown rather than
converting raw cosine distance into a confidence score. Day 3 remains
incomplete until the real draft path, retrieval-backed citations, and endpoint
tests are completed.

Exit evidence: `/v1/support/draft` uses retrieved source chunks for the selected domains and does not fabricate or fall back to a source when evidence is absent.

## Day 4 — Evaluate retrieval and grounded generation

Learning focus: retrieval recall is not the same as answer groundedness; citation IDs are not claim entailment.

- [x] Measure retrieval Recall@k against the labeled query set.
- [x] Sweep cosine-distance cutoffs as a source-presence diagnostic only; do not treat distance as answer confidence.
- [x] Measure citation correctness separately from groundedness.
- [x] Add account-recovery and email-change cases, plus cases where the corpus intentionally lacks an answer.
- [ ] Check that unsupported questions trigger the defined safe behavior and high-risk cases still require review.
- [ ] Review evaluator limitations; do not present lexical checks as semantic proof.

Retrieval baseline (2026-10-10): the same 12 labeled queries were evaluated at
k=1, 2, and 3; 10 cases have expected source IDs and two are intentionally
out-of-corpus. Mean source Recall@k was 0.85, 1.00, and 1.00; mean unique-source
precision@k was 1.00, 0.90, and 0.77, respectively. All three recall results
meet the 0.75 target. On this dataset, k=2 retained the recall of k=3 with fewer
non-expected sources; that is a dataset-specific observation, not a production
setting decision. Both out-of-corpus questions still returned nearest
neighbors, so these retrieval metrics do not demonstrate answerability or safe
abstention. No evidence cutoff is applied. See the
[retrieval evaluation artifact](./evals/results/retrieval-smoke-20261010T220934Z.json).

Distance-cutoff diagnostic (2026-10-10): after one unscored warm-up request,
the k=1 distances were swept against the dataset's expected-source labels. An
in-sample cutoff of 0.472662 separated all 10 cases with expected sources from
the two cases without one. This is not a calibrated result: the cutoff was
evaluated on the same 12 cases, and a single false accept would change the
no-source error rate by 50 percentage points. Most importantly, source presence
is not answerability: the reset-expiry case has an expected account-recovery
source, but that source does not state an expiry duration. No cutoff was
selected or added to the API. See the [warm retrieval run](./evals/results/retrieval-smoke-threshold-20261010T224232Z.json)
and [offline cutoff sweep](./evals/results/retrieval-distance-threshold-20261010T224246Z.json).

Risk preference (2026-10-10): false accepts are considered costlier than false
rejects, so a future evidence gate should favor conservative human escalation
when retrieval is uncertain. This is an evaluation preference, not a numeric
cutoff or authorization for automatic rejection.

Support-draft quality baseline (2026-10-10): groundedness v1 passed 2/3 cases
(66.7% pass rate); citation correctness passed 3/3 (100%). The `g-001`
groundedness case missed the literal phrase "human review" even though the
draft said the team would review the case manually; its expected sources and
citation contract passed. This is a lexical false negative. Conversely, a
groundedness pass is not proof of claim support because the evaluator only
checks listed phrases. The two evaluators used separate API calls and datasets
with only two overlapping questions, so their aggregate rates are not a
same-draft comparison. The draft endpoint still uses `StubRetriever`; this
does not validate the deferred pgvector draft path. See the
[groundedness run](./evals/results/groundedness-20261010T225850Z.json) and
[citation run](./evals/results/citation-correctness-20261010T230248Z.json).

Exit evidence: report results against existing targets (retrieval recall >= 0.75, groundedness >= 0.90, citation correctness >= 0.95) and clearly document any misses.

## Day 5 — Diagnose review rate and benchmark latency

Learning focus: confidence calibration, review capacity, and controlled performance experiments.

- [ ] Extend evaluation results to include per-case intent, risk level, answer confidence, review triggers, citation-contract status, and model used; avoid putting full drafts in operational metrics.
- [ ] Analyze why Week 2 escalated 20/20 drafts. Do not tune thresholds until the trigger distribution and representative workload are understood.
- [ ] Check whether `num_predict=64` limits answer completeness before treating it as a production setting.
- [ ] Run one controlled model comparison on the same questions and retrieved evidence. Hold prompt, thinking mode, token budget, and hardware constant; change only model size.
- [ ] Record sample count, warm/cold model state, p50/p95, quality results, and the 8-second p95 target. Treat this as a local experiment, not a load test.

Exit evidence: review behavior has a per-case explanation, and the model comparison reports both latency and quality without claiming a result from a single changed variable.

## Week 3 exit criteria

- [ ] `/v1/support/draft` uses real pgvector retrieval for account recovery and billing; citations map to stored chunks. `StubRetriever` is not on the user-facing runtime path.
- [ ] The fixed evaluation set covers answerable and unsupported questions.
- [ ] Retrieval, citation, groundedness, and review behavior are reported as distinct measurements.
- [ ] Missing evidence follows a safe, tested path.
- [ ] A controlled latency/quality experiment is recorded; any remaining SLO gap is explicit.
- [ ] No claim of production-scale readiness is made without representative workload, capacity, security, and operational evidence.

## Focused references

- [RAG: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [pgvector](https://github.com/pgvector/pgvector)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Google SRE: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- Optional conceptual reading only: [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) and [MCP](https://modelcontextprotocol.io/introduction). No integration is planned for Week 3.
