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
- [ ] Select a small set of synthetic or approved account-recovery and billing policies.
- [ ] Create a fixed query set containing answerable, ambiguous, and out-of-corpus questions.
- [ ] For each case, record expected source IDs, supported facts, unsupported claims to avoid, and expected review/abstention behavior.

Exit evidence: versioned source documents and a reviewed evaluation dataset are checked in before retrieval implementation.

## Day 2 — Embed and index documents

Learning focus: embeddings, chunking, vector dimensions, similarity measures, and metadata/versioning tradeoffs.

- [ ] Read the relevant [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) and [pgvector documentation](https://github.com/pgvector/pgvector).
- [ ] Choose and record a local embedding model, its version, and vector dimension.
- [ ] Chunk the selected documents and preserve stable source/version/chunk IDs, checksums, effective dates, and access-scope metadata.
- [ ] Store embeddings in PostgreSQL/pgvector with idempotent ingestion behavior.
- [ ] Test re-ingestion, document updates, and embedding-dimension mismatch handling.

Exit evidence: indexed chunks can be traced to their source document and version.

## Day 3 — Implement the real retrieval path

Learning focus: query embeddings, top-k retrieval, metadata filters, and evidence sufficiency.

- [ ] Embed a query and retrieve the nearest eligible chunks from pgvector.
- [ ] Replace the runtime `StubRetriever` binding with the pgvector retriever for `/v1/support/draft` and `/v1/retrieval/query`, while retaining the stub as a test fixture.
- [ ] Return citations from retrieved chunk metadata, not hard-coded source lists.
- [ ] Define behavior for empty or weak evidence: ask a clarifying question, abstain, or require human review.
- [ ] Add endpoint-level tests proving `/v1/support/draft` receives real retrieved chunks and citations, plus tests for filtering and no-evidence behavior. Out-of-scope requests must not silently fall back to static stub evidence.

Exit evidence: `/v1/support/draft` uses retrieved source chunks for the selected domains and does not fabricate or fall back to a source when evidence is absent.

## Day 4 — Evaluate retrieval and grounded generation

Learning focus: retrieval recall is not the same as answer groundedness; citation IDs are not claim entailment.

- [ ] Measure retrieval Recall@k against the labeled query set.
- [ ] Measure citation correctness separately from groundedness.
- [ ] Add account-recovery and email-change cases, plus cases where the corpus intentionally lacks an answer.
- [ ] Check that unsupported questions trigger the defined safe behavior and high-risk cases still require review.
- [ ] Review evaluator limitations; do not present lexical checks as semantic proof.

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
