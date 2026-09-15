# Experiment 01 - Chunk Size and Overlap Sweep

## Purpose
Build intuition for chunk token targets and overlap behavior before integrating real embeddings/retrieval evals.

## Parameters
- target_chunk_tokens: [250, 450, 700]
- overlap_tokens: [0, 50, 100]

## Metrics captured
- total_chunks
- total_estimated_tokens
- avg_chunk_tokens_estimate

## Hypotheses
1. Increasing target_chunk_tokens should reduce total_chunks.
2. Increasing overlap_tokens should increase total_estimated_tokens.
3. Larger overlap may preserve boundary context but increases redundancy.

## How to run
1. Start API:
   - `docker compose up -d api` (or your existing full stack command)
2. Run:
   - `python scripts/ingestion_preview_sweep.py`

## Interpretation guide
- If total_chunks is too high, retrieval may become noisy/costly.
- If total_chunks is too low, chunks may become semantically broad and less precise.
- Overlap should be just enough to protect boundary continuity without large token bloat.

## Run results (2026-09-15)

| target_chunk_tokens | overlap_tokens | total_chunks | total_estimated_tokens | avg_chunk_tokens_estimate |
|---:|---:|---:|---:|---:|
| 250 | 0 | 13 | 2465 | 189.62 |
| 250 | 50 | 15 | 3007 | 200.47 |
| 250 | 100 | 19 | 3944 | 207.58 |
| 450 | 0 | 9 | 2467 | 274.11 |
| 450 | 50 | 9 | 2714 | 301.56 |
| 450 | 100 | 10 | 3059 | 305.90 |
| 700 | 0 | 7 | 2469 | 352.71 |
| 700 | 50 | 7 | 2618 | 374.00 |
| 700 | 100 | 7 | 2766 | 395.14 |

## Findings

1. Increasing `target_chunk_tokens` reduced chunk count (13 -> 9 -> 7 at overlap 0), matching expectation.
2. Increasing `overlap_tokens` increased total token volume due to duplicated boundary text.
3. Overlap cost impact is largest when chunk count is already high (for example, target 250).
4. Base token totals are similar across targets at overlap 0 because the same source text is being represented with different split granularity.

## Decision for v1 defaults

- Keep the current v1 default: `target_chunk_tokens = 450`
- Keep overlap in the moderate range: `overlap_tokens = 50-75`

Rationale:
- `450` gives a balanced chunk count without heavy token bloat.
- moderate overlap protects boundary continuity without the high redundancy observed at `100`.
