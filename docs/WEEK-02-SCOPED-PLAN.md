# Week 02 Scoped Plan (Execution-Focused)

Date: 2026-09-22

Execution tracker:
- `docs/WEEK-02-EXECUTION-CHECKLIST.md`

## Week 02 objective

Move from scaffold/stub behavior to **real runtime integration** while keeping evaluation-first discipline:
- real model path (Ollama),
- real persistence path (Postgres),
- first practical Redis usage,
- then quality deltas measured against Week 01 baseline.

## Why this scope

Week 01 proved contracts, policy gates, and observability.  
Week 02 must now prove the system under real dependencies, otherwise quality metrics remain disconnected from production behavior.

## In-scope deliverables

1. Real Ollama provider integrated behind existing LLM interface
2. Postgres persistence for draft/review/audit events
3. Redis integration for one concrete control path (idempotency or short-lived cache)
4. Groundedness evaluator v1 and citation correctness evaluator v1
5. Retrieval robustness improvements for known failure cluster
6. Week 02 baseline + SLO delta report

## Out-of-scope (defer)

- LangGraph migration
- MCP tool-server integration
- persistent metrics backend (Prometheus/Grafana)
- multi-tenant auth/RBAC hardening

## Execution sequence (incremental commits)

## Commit 1: Real model usage (Ollama provider)
- Add `OllamaLLMProvider` implementation.
- Keep current stub provider as explicit fallback.
- Wire provider selection via configuration.
- Verify support draft path works end-to-end with model response.

## Commit 2: Draft/audit persistence (Postgres)
- Add repository layer for support draft records and review events.
- Persist trace-linked draft and review payloads.
- Keep schema-compatible writes with existing `audit_events` model.

## Commit 3: Redis practical integration
- Add one concrete Redis use:
  - idempotency guard for `/v1/support/review`, or
  - short-lived cache for retrieval query results.
- Add failure-safe behavior when Redis is unavailable.

## Commit 4: Groundedness + citation correctness evaluators
- Add datasets:
  - `docs/evals/groundedness-v1.jsonl`
  - `docs/evals/citation-correctness-v1.jsonl`
- Add scripts:
  - `scripts/groundedness_eval.py`
  - `scripts/citation_correctness_eval.py`

## Commit 5: Retrieval robustness improvements
- Address known phrase variants from Week 01 failures.
- Re-run smoke eval and document before/after delta.

## Commit 6: Week 02 baseline + SLO delta report
- Capture baseline with non-zero support draft traffic.
- Compare against Week 01 artifact and targets.
- Publish SLO delta report with pass/watch/not-measured.

## Success criteria for Week 02

Minimum:
- Support draft path uses real Ollama provider in normal mode.
- Support draft/review lifecycle persists core events to Postgres.
- One Redis-backed reliability/perf control is active and tested.
- Groundedness and citation correctness are measured and reported.
- Retrieval smoke pass consistency improves from Week 01 baseline.
- Updated baseline includes non-zero `support_draft_total`.

Stretch:
- retrieval failure cluster reduced to <= 1 phrase variant
- repeatable one-command quality regression run for local validation

## Risks and mitigations

1. Risk: model integration increases latency variance  
   Mitigation: keep stub fallback and track p50/p95 deltas per run.

2. Risk: persistence integration introduces write failures  
   Mitigation: explicit error surfacing + audit-safe failure handling.

3. Risk: Redis dependency adds operational fragility  
   Mitigation: degrade gracefully and cover with failure drill scenario.

4. Risk: scope expansion into framework migration too early  
   Mitigation: keep LangGraph/MCP deferred until Week 02 metrics stabilize.

## Week 02 done definition

Week 02 is complete when:
- all in-scope runtime integrations are committed and verified,
- quality deltas are measured against Week 01 baseline,
- Week 03 priorities are chosen from evidence, not assumptions.
