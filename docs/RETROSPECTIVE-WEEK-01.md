# Week 01 Retrospective: Architecture Lessons Learned

Date: 2026-09-22

## Lesson 1: Deterministic contracts before intelligence reduced failure risk

We introduced explicit contracts before adding complexity:
- retrieval API contract
- ingestion preview contract
- review status contract
- audit event payload contract

Why this mattered:
- easier debugging
- safer incremental changes
- fewer “silent behavior shifts”

Evidence:
- retrieval smoke evaluator (`docs/evals/retrieval-smoke-v1.jsonl`) consistently detected 4 phrase-variant failures.
- contract-level checks (citation contract, review taxonomy) prevented ambiguous or unsafe outputs.

## Lesson 2: Observability-first workflow improved operational confidence

Adding health validation, structured logs, metrics, and failure drills early gave objective visibility:
- stack health validation workflow
- request lifecycle logs
- metrics endpoint (`/v1/metrics`)
- dependency failure drill

Why this mattered:
- fast pass/fail readiness checks
- clear incident triage path
- measurable baseline instead of subjective status

Evidence:
- baseline artifact (`docs/evals/results/baseline-20260922T212811Z.json`) captured retrieval, latency, and reliability signals.
- failure drill validated outage detection + recovery behavior.

## Week 2 implication

Prioritize measurable retrieval robustness improvements and deeper eval coverage:
1. improve duplicate-charge phrase matching in retrieval logic
2. add groundedness/citation-correctness evals
3. capture draft-path metrics with non-zero support traffic