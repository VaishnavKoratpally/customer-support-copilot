# ADR-005: Routing threshold defaults for v0

Date: 2026-09-16
Status: Accepted

## Context
The support draft flow needs deterministic routing and review gates before learned calibration is available. Thresholds must balance safety, review load, and response speed.

## Decision
Use the following defaults:

- retrieval_confidence_threshold = 0.55
  - if retrieval confidence < 0.55, switch to escalation model path
- answer_confidence_threshold = 0.65
  - if answer confidence < 0.65, require human review
- high-risk intents always require human review regardless of confidence
- missing citations always require human review with escalation reason `missing_citations`

## Options considered
1. Aggressive automation (lower review thresholds)
2. Conservative safety-first thresholds (chosen)
3. Fully dynamic thresholds from day 1

## Tradeoffs
### Benefits
- predictable, auditable behavior
- strong safety posture for high-risk support categories
- easier debugging with deterministic gates

### Costs
- higher human-review volume early on
- some low-confidence but correct drafts still escalated

### Risks
- thresholds may be too strict for low-risk FAQ traffic
- confidence formula may not reflect true uncertainty without calibration

## Rollback trigger
If review queue volume is consistently too high without corresponding safety gains, tune thresholds using eval + reviewer feedback and publish ADR update.

## Validation metrics
- high-risk mandatory review compliance = 100%
- citation contract compliance = 100%
- pass rate on retrieval smoke eval improves over time
- human override/reject trends decrease across iterations