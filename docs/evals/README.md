# Retrieval smoke eval dataset

Dataset file:
- `retrieval-smoke-v1.jsonl`

Run evaluator from repository root:

```powershell
python scripts/retrieval_smoke_eval.py
```

Optional arguments:

```powershell
python scripts/retrieval_smoke_eval.py --api-base-url http://localhost:8000
python scripts/retrieval_smoke_eval.py --dataset docs/evals/retrieval-smoke-v1.jsonl
```

Exit codes:
- `0`: all cases passed
- `1`: one or more cases failed
- `2`: dataset parsing/input error
- `3`: API connectivity or endpoint error

