# Baseline vs SLO Comparison (2026-09-22)

Source baseline artifact:
- `docs/evals/results/baseline-20260922T212811Z.json`
- Git SHA in artifact: `7cd25a2`

## Summary

- Baseline is **partially compliant** with current v1 SLOs.
- Operational and latency signals are healthy.
- Retrieval quality is acceptable by average recall but not robust enough by pass consistency.
- Several quality/safety targets remain unmeasured in this run.

## SLO comparison table

| Category | Target | Baseline value | Status | Notes |
|---|---|---:|---|---|
| Retrieval quality | Recall@5 >= 0.75 | Avg recall = 0.80 | ✅ Pass | Meets threshold, but 4/20 cases failed. |
| Retrieval consistency | Smoke pass rate (informal) | 80% (16/20) | ⚠️ Watch | Failures clustered in duplicate-charge phrasing variants. |
| API error rate | <= 2% | 0.0% | ✅ Pass | No 5xx observed in snapshot. |
| Latency p50 | <= 4s | 1.44ms | ✅ Pass | Well below threshold. |
| Latency p95 | <= 8s | 4.82ms | ✅ Pass | Well below threshold. |
| Escalation rate | <= 20% steady state | N/A (`support_draft_total=0`) | ⚪ Not measured | No draft traffic captured in this snapshot. |
| Groundedness pass rate | >= 0.90 | N/A | ⚪ Not measured | No groundedness evaluator run yet. |
| Citation correctness | >= 0.95 | N/A | ⚪ Not measured | Requires citation quality evaluator. |
| Hallucination rate | <= 0.08 | N/A | ⚪ Not measured | Requires dedicated generation eval set. |
| High-risk review compliance | 100% | N/A | ⚪ Not measured | Need review flow compliance checks. |
| Low-confidence review compliance | 100% | N/A | ⚪ Not measured | Need policy conformance evals. |

## Key findings

1. Retrieval is **good enough to continue**, but still has phrase sensitivity gaps.
2. Observability stack is producing useful operational metrics.
3. Current baseline does not yet represent end-to-end support draft traffic.
4. Day 7 remaining items should focus on measured lessons + Week 2 evaluation plan.

## Recommended follow-up (Week 2 input)

1. Improve retrieval matching for duplicate-charge variants.
2. Add groundedness/citation correctness evaluator.
3. Capture baseline with non-zero support draft traffic.
4. Add compliance checks for high-risk and low-confidence review gates.