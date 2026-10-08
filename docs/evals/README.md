# Evaluation datasets and runbooks

## Week 3 vector retrieval diagnostic

Dataset: `rag-week3-v1.jsonl`

```powershell
python scripts/retrieval_smoke_eval.py
```

Optional arguments:

```powershell
python scripts/retrieval_smoke_eval.py --api-base-url http://localhost:8000
python scripts/retrieval_smoke_eval.py --dataset docs/evals/rag-week3-v1.jsonl
```

The diagnostic reports source Recall@k and unique-source precision@k for cases
with expected retrieval sources. These metrics deduplicate source IDs among
retrieved chunks, so they are source-level rather than chunk-level metrics. For
cases labeled with no expected sources, it reports the nearest cosine distance
and retrieved sources only; it does not classify the case as supported or
unsupported. No confidence score or evidence cutoff is applied. Choose a cutoff
only after inspecting and evaluating the distance distributions.
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
