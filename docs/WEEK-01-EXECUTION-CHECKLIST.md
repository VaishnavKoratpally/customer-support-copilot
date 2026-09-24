# Week 1 Execution Checklist (Day-by-Day)

Use this checklist as your first execution sprint.

## Day 1 - Problem framing
- [x] Finalize support domain and top 25 intents
- [x] Define unsupported intents for v1
- [x] Write v1 success criteria (latency, quality, safety, cost)
- [x] Create ADR for domain scope decisions

Exit criteria:
- You can explain why each supported intent is included.

## Day 2 - Data and schema foundation
- [x] Define ticket, message, and audit event schemas
- [x] Define source document schema for ingestion
- [x] Define chunk metadata fields (doc type, policy version, date, scope)
- [x] Create ADR for schema boundaries

Exit criteria:
- Every generated answer can be traced to source documents.

## Day 3 - Retrieval baseline
- [x] Implement initial chunking policy
- [x] Create ingestion + embedding pipeline skeleton
- [x] Define retrieval API contract
- [x] Build 20-query retrieval smoke eval set

Exit criteria:
- Retrieval returns relevant evidence for most known queries.

## Day 4 - Prompting and answer policy
- [x] Create prompt templates for grounded answer generation
- [x] Enforce citation-required output contract
- [x] Define confidence scoring method v0
- [x] Create ADR for routing threshold defaults

Exit criteria:
- Model output includes citations and confidence consistently.

## Day 5 - Human-in-the-loop workflow
- [x] Implement mandatory review rules for high-risk intents
- [x] Implement review statuses (approve/edit/reject)
- [x] Record rejection reasons taxonomy
- [x] Define audit log payload for review actions

Exit criteria:
- No high-risk answer can bypass review.

## Day 6 - Local deployment and observability
- [x] Validate Docker Compose startup and health checks
- [x] Add structured logs for request lifecycle
- [x] Add basic metrics (latency, escalation rate, error rate)
- [x] Run a failure drill (dependency unavailable)

Exit criteria:
- You can detect and explain failures quickly.

## Day 7 - Eval-first discipline and retrospective
- [x] Run baseline evals and save metrics
- [x] Compare against SLO targets
- [x] Log 2 architecture lessons learned
- [x] Plan Week 2 scope

Exit criteria:
- You have metrics + decisions to justify next changes.
