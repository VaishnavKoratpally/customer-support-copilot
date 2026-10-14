# Evaluation datasets and runbooks

## Result retention

Evaluation datasets and gold labels are versioned inputs. Generated result
JSONs under `docs/evals/results/` are local, Git-ignored outputs; retain useful
runs for debugging and record key conclusions in this runbook or the execution
checklist. Existing committed baseline snapshots remain tracked. A fresh
checkout does not contain the newer local runs: generate a development pilot
before using its cached results as profiler input.

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

Development prompt calibration (2026-10-14): stronger decision rules,
ordered instructions, synthetic few-shot examples, and a proposal-field-order
experiment did not pass the five-case pilot. One complete run regressed to
2/5; other variants mixed clarification with facts, duplicated an answer,
or made a false-sufficient decision. The original prompt and schema order
were restored rather than retaining weaker behavior. Gold labels, quote
validation, and aggregation rules were unchanged; the held-out set was not
rerun or used for tuning. The restored five-case Qwen3:4b baseline again
matched 3/5 statuses, with 0/4 false-sufficient decisions, 6/6 gold quotes,
and mean complete assessment time of 3.328 s.

A temporary Qwen3:14b comparison on just the two misses matched the expiry
case but returned `insufficient` instead of `clarification_needed` for the
ambiguous-access case: 1/2 status matches, 0/2 false-sufficient decisions.
Both outputs completed without truncation. Complete assessment times were
11.365 s and 190.913 s; decode times were 3.545 s and 189.652 s. Ollama
reported 100% GPU placement and a 4096-token context, but hardware was not
sampled continuously during those calls, so the second call's slowdown is
not attributed to a confirmed cause. This was not a full five-case 14B run.
The application remains configured for Qwen3:4b and the assessor remains
standalone; neither model has passed the requested development target.

### Frozen held-out assessor evaluation

`evidence-assessor-heldout-v1.jsonl` and
`evidence-assessor-heldout-gold-v1.jsonl` form a separate, frozen eight-case
evaluation set. It covers all six assessor statuses, including one conflicting
evidence case. Seven cases use the live retrieval API; the conflict case uses
explicit `retrieval_fixture_hits` stored only in the evaluation dataset. Those
fixture chunks are never added to the indexed support corpus and do not test
conflict retrieval.

Run all eight cases once with the current, unchanged assessor prompt:

```powershell
docker compose run --rm --no-deps -T `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  --env PYTHONPATH=/app `
  api python /evaluation/scripts/evidence_assessor_pilot.py `
    --dataset /evaluation/docs/evals/evidence-assessor-heldout-v1.jsonl `
    --gold-dataset /evaluation/docs/evals/evidence-assessor-heldout-gold-v1.jsonl `
    --api-base-url http://host.docker.internal:8000 `
    --all-cases
```

The API must be reachable on host port `8000`; the runner calls the configured
Ollama model directly for each case. A full run makes eight assessor calls and
can take many minutes. It writes a timestamped artifact under
`docs/evals/results/`. Do not tune the prompt against this held-out set; use
the result to judge the current approach, then make changes using development
cases and evaluate them on a future independent set.

The cases are separate from the original pilot questions but reuse its
synthetic source corpus, so this is not corpus-held-out validation. Aggregate
retrieval recall, gold-quote recall, and retrieval latency include only the
seven API-backed cases. Status agreement, false-sufficient counts, and
assessor latency include the fixture case; its per-case retrieval mode is
marked `fixture`.

### Single-call assessor performance profile

Use a development case and its cached retrieval hits to profile exactly one
assessor generation without re-running retrieval or the embedding model. The
profile records whether the assessor model was already loaded, Ollama's prompt
and generated token counts, model-load/prompt-evaluation/generation durations,
and `/api/ps` model-memory data. This avoids spending another inference call
just to warm the model.

Set `$pilotArtifactName` to the filename printed by a previous development
pilot containing `bi-005`; do not use a held-out or fixture-only artifact.

```powershell
$pilotArtifactName = "evidence-assessor-pilot-<UTC timestamp>.json"

docker compose run --rm --no-deps -T `
  --volume ".\services\api\app:/app/app:ro" `
  --volume ".\scripts:/evaluation/scripts:ro" `
  --volume ".\docs\evals:/evaluation/docs/evals" `
  --env PYTHONPATH=/app `
  api python /evaluation/scripts/evidence_assessor_profile.py `
    --case-id bi-005-credit-posting-date-partial-evidence `
    --retrieval-artifact "/evaluation/docs/evals/results/$pilotArtifactName"
```

The profile reuses the saved API-retrieved chunks for the development case; its
cached retrieval latency is historical and is not remeasured. It writes a
timestamped artifact under `docs/evals/results/`. Immediately afterward,
`docker compose exec -T ollama ollama ps` reports Ollama's processor placement
(CPU/GPU split); the artifact's `size_vram` versus `size` fields provide a
memory-allocation cross-check, not a substitute for the processor report.

### Local GPU power check

Use the laptop's supplied adapter for inference, not just monitor USB-C power.
`100% GPU` describes model placement, not GPU clocks or performance; high CPU
activity alone does not establish layer offload. When throughput is unexpectedly
low, inspect `nvidia-smi -q -d PERFORMANCE,POWER,CLOCK` during generation.

A local diagnostic (2026-10-13, Qwen3:4b, RTX PRO 3000 Blackwell Laptop GPU)
compared the same cached `bi-005` prompt and model digest before and after
connecting the supplied Dell adapter. Both requests were schema-constrained,
used 1,084 prompt tokens, and started with the model unloaded. Diagnostic
options were `num_predict=128`, `num_ctx=4096`, `temperature=0`, `seed=42`,
`think=false`, and non-streaming output; the normal assessor cap was unchanged.

| Observation | Monitor-only power | Supplied Dell adapter |
| --- | ---: | ---: |
| Generated tokens | 128 | 128 |
| Generation seconds | 89.997 | 1.315 |
| Generated tokens/second | 1.422 | 97.353 |
| Client wall seconds | 112.992 | 5.012 |
| Mean GPU core clock during estimated generation | 180 MHz | 2351 MHz |
| GPU memory clock during estimated generation | 405 MHz | 11001 MHz |
| Mean GPU power during estimated generation | 15.35 W | 104.51 W |
| GPU performance state during estimated generation | P8 | P1 |

Generation throughput improved **68.45x in this capped comparison**. Windows
remained Balanced; no prompt, model, driver, or application settings changed.
The monitor-powered post-run GPU limit was 20 W, not a measured inference-time
limit; the powered generation samples reported a 105 W limit. Removing the
schema in a separate monitor-powered call did not improve throughput, but
that single comparison does not establish zero schema overhead.

This is one ordered comparison, not a repeatability benchmark. GPU readings
are whole-device and the new estimated generation window contains only four
samples, at a different cadence from the baseline. Both outputs stopped at
the 128-token cap: **5.012 s is not a full assessor latency result**, and no
quality or integration gate changed.

The subsequent five-case development pilot used the normal 1024-token cap
and completed all outputs without truncation. Mean decode time was 3.081 s,
mean complete assessment time was 3.711 s (previously 210.738 s), and the
whole run took 20.645 s. Status agreement remained 3/5, with 0/4
false-sufficient decisions and 6/6 gold quotes retrieved. The same expiry
and ambiguous-access classifications were wrong: adequate power restored
usable iteration speed, not assessor accuracy.
