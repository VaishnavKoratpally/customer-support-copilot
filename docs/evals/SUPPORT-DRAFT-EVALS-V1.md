# Support Draft Evaluations v1

These evaluators call the live `POST /v1/support/draft` endpoint. They assess draft text and citation IDs using deterministic checks; they do not use an LLM judge.

## How to interpret the two metrics

Citation correctness checks whether the returned source IDs match the expected
IDs. It does not inspect the draft text, so correct citations do not prove that
the draft's claims are supported.

Groundedness v1 checks literal required and forbidden phrases, expected-source
coverage, and the API citation contract. It is a regression heuristic, not a
semantic support check: equivalent paraphrases can fail a literal phrase check,
and unsupported wording not covered by a forbidden phrase can pass.

The evaluators use different datasets and call the draft endpoint separately.
Their run-level pass rates are not a paired comparison of the same drafts.
`scripts/test_draft_quality_metrics.py` demonstrates the distinction on one
synthetic response without calling the model.

## Groundedness criteria

Dataset: `groundedness-v1.jsonl`

Each case contains a question, required phrases, forbidden phrases, and expected source IDs. The evaluator compares phrases case-insensitively against the returned draft and checks that every expected source ID is present and the API reports `citation_contract_passed: true`.

For each case:

- A required phrase passes when it occurs as a literal substring in the draft.
- A forbidden phrase passes when it does not occur as a literal substring in the draft.
- Source coverage passes when the expected source IDs are a subset of the response's `citation_source_ids`.
- Citation contract passes when the API returns `citation_contract_passed: true`.
- The case passes only when every check passes.
- The case score is `passed checks / total checks`; the run pass rate is `passed cases / evaluated cases`.

This is a lexical regression heuristic, not semantic verification that every claim is supported. It can mark a valid paraphrase as a miss and cannot identify unsupported claims that are not listed as forbidden phrases. Keep requirements concise and grounded in the current policy evidence.

## Citation correctness criteria

Dataset: `citation-correctness-v1.jsonl`

For each case, let `E` be the set of expected citation source IDs and `A` the set returned in `citation_source_ids`:

- Precision = `|A ∩ E| / |A|` (zero when no citations are returned).
- Recall = `|A ∩ E| / |E|`.
- F1 = harmonic mean of precision and recall (zero when both are zero).
- The case passes when every expected ID is present, the citation contract passes, and no unexpected IDs are present unless `allow_extra_citations` is true.
- The case score is F1; the run pass rate is `passed cases / evaluated cases`.

IDs are compared as sets, so repeated occurrences of the same source ID do not change the score. Citation correctness evaluates attribution IDs, not whether the cited document semantically supports each sentence.

## Running and artifacts

From the repository root, with the API reachable on host port `8000`:

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  api python /evaluation/scripts/groundedness_eval.py `
    --dataset /evaluation/docs/evals/groundedness-v1.jsonl `
    --api-base-url http://host.docker.internal:8000

docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  api python /evaluation/scripts/citation_correctness_eval.py `
    --dataset /evaluation/docs/evals/citation-correctness-v1.jsonl `
    --api-base-url http://host.docker.internal:8000
```

Each run writes a timestamped JSON artifact under `docs/evals/results/`.
Groundedness artifacts include the returned draft text; citation-correctness
artifacts record citation IDs and scores. Quality failures still produce an
artifact.

Optional arguments:

```powershell
python scripts/groundedness_eval.py --api-base-url http://localhost:8000 --timeout-seconds 600
python scripts/citation_correctness_eval.py --dataset docs/evals/citation-correctness-v1.jsonl --output docs/evals/results/citation-manual.json
```

Exit codes:

- `0`: all evaluated cases passed.
- `1`: evaluation completed, but one or more cases failed.
- `2`: invalid/missing dataset or artifact write failure.
- `3`: support draft API request failed; a partial artifact is saved when possible.

Use synthetic or approved evaluation inputs only. Artifacts contain generated draft text; do not evaluate or save real customer messages without following the project's data-handling requirements.
