# Retrieval Robustness Check — 2026-10-04

## Objective
Check whether the deterministic billing-query rule fixes the phrase variants that failed in the Week 1 retrieval baseline.

## Change tested
A shared billing-dispute query rule is used by both retrieval and routing. This keeps the selected billing evidence consistent with high-risk billing-dispute classification.

## Results

| Run | Cases passed | Pass rate | Average recall |
|---|---:|---:|---:|
| Week 1 baseline (`baseline-20260922T212811Z.json`) | 16/20 | 80% | 0.80 |
| Day 5 working-tree run | 20/20 | 100% | 1.00 |

Previously failing cases that passed:
- `rq-003`: two charges for one invoice
- `rq-005`: duplicate renewal billing
- `rq-007`: two transactions for one subscription
- `rq-008`: duplicate billing charge

The two general-help control questions also continued to return `general-help-01` and `general_support` / low risk.

## Interpretation
On this 20-case smoke dataset, phrase coverage improved: all expected sources were retrieved, with no misses.

## Limitations
This validates deterministic rules in the stub retriever against a small, curated dataset. It does not demonstrate semantic/vector retrieval quality, broad paraphrase coverage, or production-scale performance. The Day 5 result was measured on the working tree before its changes were committed.

## Reproduce
From the repository root, with the API running:
## Mandatory-review policy compliance

Command, run from `services/api`:
`python -m unittest discover -s tests -v`

Result: 6 tests passed.

Verified high-risk intents require review; low confidence and missing citations each trigger review; a confident, cited, low-risk case does not require review; confidence exactly at the threshold is not considered below it; and multiple applicable triggers are all reported.

```powershell
python scripts/retrieval_smoke_eval.py