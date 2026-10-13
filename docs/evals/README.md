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
    --top-k-values 1 2 3 `
    --warm-up
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
`--warm-up` makes one unscored request before measurements and records that in
the artifact; use it when analyzing cosine distances. Pass `--output <path>` to
choose a different artifact path. The running API must be reachable on host
port `8000`.
`retrieval-smoke-v1.jsonl` is a legacy stub-era dataset and is not compatible
with the vector-backed endpoint.

### Offline cosine-distance cutoff diagnostic

This diagnostic asks only whether a case has a labeled expected source. It
sweeps the observed cutoffs and reports false accepts and false rejects; it
does not select or enforce a production threshold.

```powershell
$retrievalArtifactName = "retrieval-smoke-threshold-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')).json"

docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  api python /evaluation/scripts/retrieval_smoke_eval.py `
    --dataset /evaluation/docs/evals/rag-week3-v1.jsonl `
    --api-base-url http://host.docker.internal:8000 `
    --top-k-values 1 `
    --warm-up `
    --output "/evaluation/docs/evals/results/$retrievalArtifactName"

docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  api python /evaluation/scripts/retrieval_distance_threshold_eval.py `
    --retrieval-artifact "/evaluation/docs/evals/results/$retrievalArtifactName" `
    --dataset /evaluation/docs/evals/rag-week3-v1.jsonl `
    --top-k 1
```

The positive label means that the dataset names at least one expected
retrieval source. That is **not** the same as having enough evidence to answer:
for example, the reset-link-expiry case has an expected account-recovery source,
but that source does not specify the expiry duration. Raw cosine distance is a
retrieval signal, not answer confidence. This small dataset has only two cases
with no expected source, so an apparently clean cutoff is exploratory and must
not be treated as calibrated or production-ready.

## Support draft quality evaluations

See [SUPPORT-DRAFT-EVALS-V1.md](SUPPORT-DRAFT-EVALS-V1.md) for scoring criteria, limitations, commands, exit codes, and artifact format.

Datasets:
- `groundedness-v1.jsonl`
- `citation-correctness-v1.jsonl`

The metrics answer different questions: citation correctness checks source
IDs; groundedness v1 checks listed phrases and citation coverage. Neither is a
semantic proof that every claim follows from the cited text. See
[SUPPORT-DRAFT-EVALS-V1.md](SUPPORT-DRAFT-EVALS-V1.md) for criteria and
limitations.

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

Each evaluator writes a timestamped artifact under `docs/evals/results/`.

## Claim-level evidence assessor pilot

Run the five-case pilot from the repository root in PowerShell:

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  --env PYTHONPATH=/app `
  api python /evaluation/scripts/evidence_assessor_pilot.py `
    --dataset /evaluation/docs/evals/rag-week3-v1.jsonl `
    --gold-dataset /evaluation/docs/evals/evidence-assessor-gold-v1.jsonl `
    --api-base-url http://host.docker.internal:8000
```

The running API must be reachable on host port `8000`, and the API service's
configured Ollama URL must be reachable from Docker. The one-off container
mounts the evaluator read-only and writes its timestamped artifact under
`docs/evals/results/`; it does not add an API endpoint or change the running
API image.

By default, the pilot runs one case for each available outcome:
`sufficient`, `insufficient`, `clarification_needed`, `partial`, and `none`.
The separate `evidence-assessor-gold-v1.jsonl` file is joined by case ID and
validated against the retrieval dataset's questions and aggregate status. Its
atomic labels record each requested information item, finding, answer where
supported, exact evidence quotes using stable source/section references,
supporting facts, and clarification topics. The pilot includes these labels in
the result artifact and checks whether each gold evidence quote was retrieved.
It also reports false-sufficient outcomes separately from exact status
mismatches: a conservative `none` result for an `insufficient` case is still a
status error, but it is not a false-sufficient result.

Requested-information alignment, answer/fact correctness, unsupported
assertions, and scenario-specific action fit remain manual review fields in
the artifact; labels do not make semantic equivalence safe to score with
string matching. The dataset's action labels are more specific than the
assessor's generic actions. This pilot also does not create a human-review
task. The dataset has no conflicting-evidence case, so that assessor behavior
is not covered by this gold set.

Use `--case-id <id>` (repeatable) to run selected cases, or `--all-cases` to
run the complete dataset. A full run makes twelve assessor calls and can take
many minutes with the local model. Run annotation-contract tests without model
inference from the repository root:

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/app/scripts:ro" `
  --volume ".\docs\evals:/app/docs/evals:ro" `
  --env PYTHONPATH=/app `
  api python -m unittest discover -s scripts -p "test_evidence_assessor_pilot.py" -v
```
