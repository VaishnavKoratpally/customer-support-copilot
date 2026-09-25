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
- [ ] Add repository layer for draft/review/audit persistence
- [ ] Persist support draft outputs with trace linkage
- [ ] Persist support review outcomes with audit payload linkage
- [ ] Validate read/write behavior against running Postgres instance

Exit criteria:
- Core support lifecycle events are persisted and queryable from Postgres.

## Day 3 - Redis practical integration
- [ ] Choose one concrete Redis role (idempotency guard or retrieval cache)
- [ ] Implement Redis integration on selected path
- [ ] Add explicit fallback behavior when Redis is unavailable
- [ ] Validate behavior with Redis up/down scenarios

Exit criteria:
- Redis-backed control works and fails gracefully without unsafe behavior.

## Day 4 - Groundedness and citation correctness evaluators
- [ ] Define groundedness eval criteria and scoring rules
- [ ] Create `docs/evals/groundedness-v1.jsonl` and `docs/evals/citation-correctness-v1.jsonl`
- [ ] Implement `scripts/groundedness_eval.py` and `scripts/citation_correctness_eval.py`
- [ ] Run both evaluators and save output artifacts

Exit criteria:
- Groundedness and citation correctness are measurable via repeatable commands.

## Day 5 - Retrieval robustness + policy compliance checks
- [ ] Analyze retrieval failure cluster from Week 01 baseline
- [ ] Improve phrase robustness in retrieval logic
- [ ] Re-run retrieval smoke and document before/after delta
- [ ] Run mandatory-review policy compliance checks and record pass/fail summary

Exit criteria:
- Retrieval consistency and policy compliance both show measurable improvement.

## Day 6 - Week 2 baseline capture and SLO delta report
- [ ] Generate support-draft traffic before baseline snapshot
- [ ] Capture Week 2 baseline artifact with non-zero `support_draft_total`
- [ ] Compare Week 2 artifact against Week 1 baseline
- [ ] Publish Week 2 SLO delta report with pass/watch/not-measured status

Exit criteria:
- Week-over-week quality/reliability movement is explicitly documented.

## Day 7 - Week 2 retrospective and Week 3 planning
- [ ] Log 2 architecture lessons learned from Week 2
- [ ] Record top unresolved risks and tradeoffs
- [ ] Propose Week 3 priorities based on measured runtime + quality gaps
- [ ] Reassess LangGraph/MCP readiness based on integration stability

Exit criteria:
- Next-week scope is evidence-driven and linked to measured outcomes.
