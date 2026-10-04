# Evaluation datasets and runbooks

## Retrieval smoke evaluation

Dataset: `retrieval-smoke-v1.jsonl`

```powershell
python scripts/retrieval_smoke_eval.py
```

Optional arguments:

```powershell
python scripts/retrieval_smoke_eval.py --api-base-url http://localhost:8000
python scripts/retrieval_smoke_eval.py --dataset docs/evals/retrieval-smoke-v1.jsonl
```

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
