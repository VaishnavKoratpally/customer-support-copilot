# Week 2 Baseline and SLO Delta (2026-10-06)

## Source and run profile

- Baseline artifact: `results/baseline-20261006T145751Z.json`
- Git SHA: `8938d01`
- Workload: 20 synthetic support-draft requests, issued sequentially
- Model: `qwen3:14b`
- Inference settings: `think=false`, `num_predict=64`
- This is a local single-client baseline, not a concurrent load test.

## Summary

- All 20 support-draft requests succeeded; the draft route recorded 0/20 5xx errors.
- Draft-route p50 was 35.01 seconds and p95 was 44.28 seconds. Both exceed the current latency targets.
- All 20 drafts required human review. This includes routine and sensitive questions; inspect per-case review triggers and confidence before interpreting the rate.
- Retrieval smoke passed 20/20 cases with average recall 1.00, up from 16/20 and 0.80 in Week 1. This result is limited to the curated deterministic stub-retrieval dataset.
- The baseline run did not score these 20 generated drafts for groundedness, citation correctness, or hallucination rate.

## SLO comparison

| Category | Target | Week 1 | Week 2 | Status | Notes |
|---|---|---|---|---|---|
| Retrieval quality | Recall@5 >= 0.75 | Avg recall 0.80 | Avg recall 1.00 | ✅ Pass | 20-case curated smoke test using deterministic stub retrieval; not semantic/vector retrieval evidence. |
| Retrieval consistency | Smoke pass rate | 16/20 (80%) | 20/20 (100%) | ✅ Pass | Known phrase variants now pass on this dataset. |
| Support-draft 5xx rate | <= 2% | N/A; no draft requests | 0/20 (0%) | ✅ Pass | Sample result, not a long-term reliability SLO. |
| Support-draft latency p50 | <= 4s | Not measured; Week 1 had no draft traffic | 35.01s | ⚠️ Watch | About 8.8x the target. |
| Support-draft latency p95 | <= 8s | Not measured; Week 1 had no draft traffic | 44.28s | ⚠️ Watch | About 5.5x the target; 20 sequential samples. |
| Human-review rate | <= 20% steady state | Not measured | 20/20 (100%) | ⚠️ Watch | Synthetic workload, but includes routine cases; investigate review triggers and confidence. |
| Groundedness | >= 0.90 | Not measured | Not measured on these 20 drafts | ⚪ Not measured | Day 4's separate 3-case evaluation is not evidence for this workload. |
| Citation correctness | >= 0.95 | Not measured | Not measured on these 20 drafts | ⚪ Not measured | Citation IDs and claim-level support were not evaluated for this run. |
| Hallucination rate | <= 0.08 | Not measured | Not measured | ⚪ Not measured | Requires a dedicated generation evaluation. |

## Interpretation and limitations

1. The support-draft route is reliable in this 20-request run, but its measured latency is substantially over target.
2. The Week 1 aggregate p50/p95 values (1.44ms/4.82ms) are not comparable to Week 2 draft-route latency: Week 1 captured zero support drafts.
3. A 100% human-review rate is a useful signal, not a steady-state estimate. The artifact records the aggregate count but not per-case review triggers or confidence.
4. The run was sequential and local. It does not establish concurrent capacity, production SLO attainment, or million-user readiness.
5. The run used `think=false` and `num_predict=64`; speed cannot be attributed to disabling thinking alone. The token cap may constrain answer completeness.
6. The separate three-prompt pilot surfaced unsupported procedural details in general-help responses and an unsupported “get back shortly” assurance. That is a qualitative pilot observation, not a score for these 20 cases. The current `general-help-01` evidence is generic; see `services/api/app/retriever.py`.

## Follow-up

- Inspect why routine as well as sensitive cases required human review; add per-case trigger/confidence reporting to future evaluation artifacts.
- Expand groundedness cases to cover account recovery and email changes, and check claim support rather than citation IDs alone.
- Evaluate model/token settings as a separate experiment after preserving this baseline.