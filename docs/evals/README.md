# Evaluation datasets and runbooks

## Week 3 vector retrieval diagnostic

Dataset: `rag-week3-v1.jsonl`

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  api python /evaluation/scripts/retrieval_smoke_eval.py `
    --dataset /evaluation/docs/evals/rag-week3-v1.jsonl `
    --api-base-url http://host.docker.internal:8000 `
    --top-k-values 1 2 3
```

The diagnostic reports source Recall@k and unique-source precision@k for cases
with expected retrieval sources. These metrics deduplicate source IDs among
retrieved chunks, so they are source-level rather than chunk-level metrics. For
cases labeled with no expected sources, it reports the nearest cosine distance
and retrieved sources only; it does not classify the case as supported or
unsupported. No confidence score or evidence cutoff is applied. Choose a cutoff
only after inspecting and evaluating the distance distributions.
The `--top-k-values` sweep runs the same labeled questions at each requested
value, isolating the effect of `top_k`; omit it to use each case's dataset
setting. The evaluator writes a timestamped JSON artifact under
`docs/evals/results/`, including per-case results and summaries by `top_k`.
Pass `--output <path>` to choose a different artifact path. The running API
must be reachable on host port `8000`.
`retrieval-smoke-v1.jsonl` is a legacy stub-era dataset and is not compatible
with the vector-backed endpoint.

## Support draft quality evaluations

See [SUPPORT-DRAFT-EVALS-V1.md](SUPPORT-DRAFT-EVALS-V1.md) for scoring criteria, limitations, commands, exit codes, and artifact format.

Datasets:
- `groundedness-v1.jsonl`
- `citation-correctness-v1.jsonl`

Run from the repository root:

```powershell
python scripts/groundedness_eval.py
python scripts/citation_correctness_eval.py
```

Each evaluator writes a timestamped artifact under `results/`.

## Claim-level evidence assessor pilot

Run the five-case pilot from the repository root in PowerShell:

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  --env PYTHONPATH=/app `
  api python /evaluation/scripts/evidence_assessor_pilot.py `
    --dataset /evaluation/docs/evals/rag-week3-v1.jsonl `
    --api-base-url http://host.docker.internal:8000
```

The running API must be reachable on host port `8000`, and the API service's
configured Ollama URL must be reachable from Docker. The one-off container
mounts the evaluator read-only and writes its timestamped artifact under
`docs/evals/results/`; it does not add an API endpoint or change the running
API image.

By default, the pilot runs one case for each available outcome:
`sufficient`, `insufficient`, `clarification_needed`, `partial`, and `none`.
It reports exact status matches, retrieved-source recall where the dataset has
expected sources, and retrieval/assessment latency. Requested-information
coverage, answer/fact correctness, unsupported
assertions, and scenario-specific action fit remain manual review fields in
the artifact; the dataset does not contain gold requested-information
decompositions, and its action labels are more specific than the assessor's
generic actions. This pilot also does not create a human-review
task. The dataset has no conflicting-evidence case.

Use `--case-id <id>` (repeatable) to run selected cases, or `--all-cases` to
run the complete dataset. A full run makes twelve assessor calls and can take
many minutes with the local model.
