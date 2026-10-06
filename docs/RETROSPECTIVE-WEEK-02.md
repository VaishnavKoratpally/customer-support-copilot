# Week 2 Retrospective: Lessons Learned

Date: 2026-10-06

## Evidence

- Week 2 baseline: [baseline-20261006T145751Z.json](./evals/results/baseline-20261006T145751Z.json), code SHA `8938d01`.
- Week 1 baseline: [baseline-20260922T212811Z.json](./evals/results/baseline-20260922T212811Z.json).
- Retrieval implementation: [retriever.py](../services/api/app/retriever.py).
- Evaluation limitations: [SUPPORT-DRAFT-EVALS-V1.md](./evals/SUPPORT-DRAFT-EVALS-V1.md).

## Week 2 outcome

- Integrated the local Ollama model path, PostgreSQL persistence, and Redis idempotency for support reviews.
- Retrieval smoke improved from 16/20 cases and 0.80 average recall to 20/20 and 1.00 on the same curated dataset. This still measures deterministic stub-retriever behavior, not vector retrieval.
- The local Qwen3:14b baseline completed 20/20 drafts with no draft-route 5xx errors. Draft-route p50 was 35.01 seconds and p95 was 44.28 seconds against a p95 target of 8 seconds.
- All 20 baseline drafts required human review. The artifact records the aggregate rate, but not per-case review triggers or confidence.
- The baseline used `think=false` and `num_predict=64`. Because both settings changed relative to the earlier pilot configuration, the speed difference cannot be attributed to either change alone.

## Architecture lessons

### 1. Citation presence is not claim-level grounding

A response can cite the expected source IDs and still add unsupported details. During the pilot, generic `general-help-01` evidence accompanied specific account instructions, and a billing draft made an unsupported “get back shortly” assurance. The citation evaluator checks attribution IDs; the current groundedness evaluator uses lexical requirements and prohibitions. Neither proves that every claim follows from its cited evidence.

**Design implication:** treat source retrieval, citation correctness, and claim-level support as separate properties. When evidence is insufficient, the system should ask, abstain, or require review rather than fill gaps from model knowledge.

### 2. SLOs must measure the critical route under a matching workload

Week 1 recorded zero support drafts, so its aggregate 4.82ms p95 did not measure draft latency. Week 2 generated draft traffic and measured the draft route separately, exposing a 44.28-second p95.

**Design implication:** define metrics for the user-critical route and generate a workload that exercises it. Keep aggregate service metrics, but do not use them as a substitute for route-specific SLO evidence.

## Unresolved risks and tradeoffs

| Priority | Risk | Evidence and tradeoff | Next action |
|---|---|---|---|
| 1 | Unsupported claims from insufficient evidence | The pilot showed plausible details not contained in retrieved context. Human review reduces risk but does not prove each claim is grounded. | Build a real, narrow support corpus; test evidence sufficiency and safe abstention. |
| 2 | Review workload and calibration | 20/20 synthetic drafts required review, including routine questions. The aggregate artifact does not show why each was escalated. Safety competes with reviewer capacity. | Record per-case intent, confidence, risk, and review triggers; do not lower thresholds based on this sample alone. |
| 3 | Draft latency exceeds target | The 44.28-second p95 is about 5.5 times the 8-second target. The run was local and sequential. | Benchmark one inference variable at a time while checking answer quality and recording model state. |
| 4 | Limited operational evidence | Metrics are process-local and the baseline is not concurrent or production-scale testing. | Keep scale claims modest; add durable metrics and load testing only when workload and deployment assumptions are defined. |

## LangGraph and MCP readiness

**Decision: defer both integrations.**

- LangGraph is not justified by the current mostly linear request flow. Revisit it if workflows need durable state, branching, retries, or pause/resume around human review.
- MCP is not justified while the service has no shared external tool surface. Revisit it when multiple clients or agents need standardized, permissioned access to systems such as orders, billing, or CRM.

These tools solve different problems: LangGraph organizes stateful workflows; MCP standardizes tool and resource access. Neither addresses the current grounding or latency gaps by itself.

## Week 3 direction

Build one real, measurable RAG vertical slice for account recovery and billing. Keep the existing provider and review-policy boundaries, use PostgreSQL/pgvector, improve evidence and evaluation first, then benchmark model latency and quality.
