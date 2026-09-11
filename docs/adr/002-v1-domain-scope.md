# ADR-002: v1 domain scope for support copilot

Date: 2026-09-11  
Status: Accepted

## Context

The project needs a constrained, realistic domain to:

- learn architecture and AI design through concrete tradeoffs,
- build measurable evaluation suites,
- avoid scope sprawl before baseline reliability exists.

## Decision

Set v1 domain to **B2B SaaS billing + account support**, with 25 defined intents and explicit unsupported intents documented in `docs/DOMAIN-SCOPE.md`.

## Options Considered

1. Broad all-in-one support domain across legal, outage, and sales operations
2. Narrow FAQ-only assistant
3. B2B SaaS billing + account support with HITL guardrails

## Tradeoffs

- Benefits:
  - high practical relevance and recurring support workflows
  - sufficient risk diversity for HITL design learning
  - measurable retrieval and escalation behavior
- Costs:
  - excludes some complex enterprise workflows in v1
  - requires clear handoff boundaries for out-of-scope requests
- Risks:
  - users may ask unsupported legal/compliance questions
  - policy changes in billing docs can affect answer reliability

## Rollback Trigger

If v1 scope causes persistent unmet demand in a specific excluded intent class and safety controls are stable, expand scope in a dedicated phase with new eval coverage.

## Validation Metrics

- intent coverage on pilot tickets >= 80%
- mandatory review compliance for high-risk intents = 100%
- unsupported-intent detection precision >= 0.90

