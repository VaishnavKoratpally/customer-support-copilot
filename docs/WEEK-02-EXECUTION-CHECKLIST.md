# Week 2 Execution Checklist (Day-by-Day)

Use this checklist as your second execution sprint.
Execution method reference:
- `docs/WEEK-02-INSTRUCTOR-MODE.md`

## Day 1 - Real model integration (Ollama)
- [x] Implement real `OllamaLLMProvider` behind existing provider interface
- [x] Add configuration switch for provider selection (real vs stub fallback)
- [x] Wire support draft path to real provider in default local mode
- [x] Validate `/v1/support/draft` response path with live Ollama runtime

Exit criteria:
- [x] Support draft flow uses real model path successfully in local runtime.

## Day 2 - Postgres persistence path
- [x] Add repository layer for draft/review/audit persistence
- [x] Persist support draft outputs with trace linkage
- [x] Persist support review outcomes with audit payload linkage
- [x] Validate read/write behavior against running Postgres instance

Exit criteria:
- Core support lifecycle events are persisted and queryable from Postgres.

## Day 3 - Redis practical integration
- [x] Choose one concrete Redis role (idempotency guard or retrieval cache)
- [x] Implement Redis integration on selected path
- [x] Add explicit fallback behavior when Redis is unavailable
- [x] Validate behavior with Redis up/down scenarios

Exit criteria:
- Redis-backed control works and fails gracefully without unsafe behavior.

## Day 4 - Groundedness and citation correctness evaluators
- [x] Define groundedness eval criteria and scoring rules
- [x] Create `docs/evals/groundedness-v1.jsonl` and `docs/evals/citation-correctness-v1.jsonl`
- [x] Implement `scripts/groundedness_eval.py` and `scripts/citation_correctness_eval.py`
- [x] Run both evaluators and save output artifacts

Exit criteria:
- Groundedness and citation correctness are measurable via repeatable commands.

## Day 5 - Retrieval robustness + policy compliance checks
- [x] Analyze retrieval failure cluster from Week 01 baseline
- [x] Improve phrase robustness in retrieval logic
- [x] Re-run retrieval smoke and document before/after delta
- [x] Run mandatory-review policy compliance checks and record pass/fail summary

Exit criteria:
- Retrieval consistency and policy compliance both show measurable improvement.

## Day 6 - Week 2 baseline capture and SLO delta report
- [x] Generate support-draft traffic before baseline snapshot
- [x] Capture Week 2 baseline artifact with non-zero `support_draft_total`
- [x] Compare Week 2 artifact against Week 1 baseline
- [x] Publish Week 2 SLO delta report with pass/watch/not-measured status

Exit criteria:
- Week-over-week quality/reliability movement is explicitly documented.

## Day 7 - Week 2 retrospective and Week 3 planning
- [x] Log 2 architecture lessons learned from Week 2
- [x] Record top unresolved risks and tradeoffs
- [x] Propose Week 3 priorities based on measured runtime + quality gaps
- [x] Reassess LangGraph/MCP readiness based on integration stability

Exit criteria:
- Next-week scope is evidence-driven and linked to measured outcomes.
