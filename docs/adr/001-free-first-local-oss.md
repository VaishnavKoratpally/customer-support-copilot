# ADR-001: Free-first local OSS runtime for v1

Date: 2026-09-11  
Status: Accepted

## Context

The project goals are to:

- deeply learn AI systems from first principles,
- remain low-cost/free-first while building,
- preserve architectural flexibility for future provider changes.

## Decision

Use a local-first stack for v1:

- Ollama for model serving
- PostgreSQL + pgvector for transactional and vector storage
- Redis for cache/queue primitives
- FastAPI as orchestration backend
- Provider abstractions to allow future hybrid routing

## Options Considered

1. Managed API-first stack (Gemini/OpenAI-only)
2. Local OSS-only stack
3. Hybrid from day 1

## Tradeoffs

- Benefits:
  - low operating cost during learning
  - strong architecture understanding through direct control
  - reduced vendor lock-in
- Costs:
  - higher operational complexity
  - potential latency/quality limits on constrained hardware
- Risks:
  - model quality may lag paid APIs in edge cases
  - throughput limits without GPU capacity

## Rollback Trigger

If v1 SLOs cannot be met after optimization (routing, caching, prompt/retrieval tuning), introduce hybrid provider fallback for high-impact requests only.

## Validation Metrics

- P95 latency <= 8s for default path
- groundedness pass rate >= 0.90
- hallucination rate <= 0.08
- escalation coverage for high-risk intents = 100%

