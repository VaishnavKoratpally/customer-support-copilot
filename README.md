# Customer Support Copilot (Human-in-the-Loop)

This repository is the implementation workspace for a production-grade, free-first customer support copilot. The design prioritizes:

- local OSS models first (Ollama)
- explicit human-in-the-loop guardrails
- measurable quality via evaluation harnesses
- architecture decisions documented with tradeoffs

## Learning and collaboration approach

This is also a deep-learning project in AI engineering and system design. See [Learning and Engineering Contract](docs/LEARNING-CONTRACT.md) for the guide-first workflow, scale assumptions, debugging practice, and expectations for using AI effectively.

## Current milestone

Local retrieval-preview and advisory reviewer-assistance milestone:

- local runtime stack (Postgres + Redis + Ollama + API) via Docker Compose
- real pgvector evidence previews without generated customer replies or confidence claims
- persisted human-review lifecycle and locally simulated delivery gates
- opt-in, recorded evidence-assessor proposals and separate reviewer feedback
- architecture docs and ADR template
- day-by-day execution checklist
- v1 domain scope selected: B2B SaaS billing + account support

## Repository layout

- `services/api`: FastAPI backend skeleton
- `docs`: architecture, ADRs, and execution checklist
- `docker-compose.yml`: local runtime

## Prerequisites

- Docker Desktop
- Python 3.11+ (for local non-container validation, optional)

## pgAdmin (Database GUI)

Open: http://localhost:5050

Login:
- Email: value of PGADMIN_DEFAULT_EMAIL
- Password: value of PGADMIN_DEFAULT_PASSWORD

Add server in pgAdmin:
- Name: support-copilot-postgres
- Host: postgres
- Port: 5432
- Maintenance DB: support_copilot
- Username: support_user
- Password: support_password

## Quick start

1) Create local env file:

```powershell
Copy-Item .env.example .env
```

2) Start infrastructure:

```powershell
docker compose up -d postgres redis ollama pgadmin
```

3) Initialize the database. The fresh schema includes the review lifecycle, evidence-assessment attempts, and reviewer feedback. When upgrading an existing Week 2 database, apply migrations in order before starting the API:

```powershell
# Fresh database
Get-Content .\services\api\db\schema.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot

# Existing Week 2 database (apply migrations in order; skip those already applied)
Get-Content .\services\api\db\migrations\001_week3_versioned_embeddings.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\002_persisted_support_review_lifecycle.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\003_simulated_support_delivery.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\004_preview_only_drafts.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\005_reviewer_evidence_assistance.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
```

If migrations `001` through `003` were already applied, run `004` and `005`.
If the database is already through `004`, run only `005`.

4) Pull recommended models inside Ollama container:

```powershell
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull qwen3:14b
docker compose exec ollama ollama pull qwen3:20b
docker compose exec ollama ollama pull qwen3-embedding:0.6b
```

5) Start API:

```powershell
docker compose up --build api
```

6) Health check:

```powershell
curl http://localhost:8000/health
```

7) Draft endpoint sample:

```powershell
curl -X POST http://localhost:8000/v1/support/draft `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"I was charged twice for my plan. Can you help?\"}"
```

The current draft endpoint is intentionally `preview_only`: it uses real
pgvector evidence but does not generate a customer answer or claim confidence.
Retrieved citations include raw cosine distance, which is not a confidence
score. A preview must be human-edited before a simulated-delivery receipt can
be created; approving the preview notice alone is not allowed.

For a generated-mode draft, when the draft response says `not_required`, or the
review response says `approved` or `edited`, use its trace ID to create a local
simulated-delivery receipt:

```powershell
curl -X POST http://localhost:8000/v1/support/simulated-deliveries `
  -H "Content-Type: application/json" `
  -d "{\"trace_id\":\"YOUR_TRACE_ID\"}"
```

This records a hash-only receipt; it does not send a message to a customer or external service. Pending or rejected drafts are refused.

## Opt-in reviewer evidence assistance (Stage A)

The assessor is an **unverified advisory aid**, not an approval oracle. The
default draft endpoint still performs retrieval only. A separate request
assesses the canonical question and full citation passages saved under a
`preview_only` trace: it does not repeat retrieval or generate a customer reply.
The proposal, derived status/action, quotes, original passages, timing metadata,
and feedback are inspectable. Even a `sufficient` proposal or
`draft_from_determined_claims` action does not authorize drafting or delivery.

After applying migration `005` and rebuilding the API, try this in PowerShell:

```powershell
$previewBody = @{
  question = "How long does the initial review take for a duplicate charge?"
} | ConvertTo-Json
$preview = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/support/draft" `
  -ContentType "application/json" -Body $previewBody

$requestId = [guid]::NewGuid().ToString()
$assessmentBody = @{
  trace_id = $preview.trace_id
  request_id = $requestId
  reviewer_id = "agent-1"
} | ConvertTo-Json
$assessment = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/v1/support/evidence-assessments" `
  -ContentType "application/json" -Body $assessmentBody

$saved = Invoke-RestMethod `
  -Uri "http://localhost:8000/v1/support/evidence-assessments/$requestId"
$saved.assessment.proposed_assessment | ConvertTo-Json -Depth 10
$saved.assessment.citations | ConvertTo-Json -Depth 10

# Submit helpful feedback only after checking the findings against the passages.
$feedbackBody = @{
  reviewer_id = "agent-1"
  verdict = "helpful"
  notes = "I checked the proposed findings against the displayed passages."
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/v1/support/evidence-assessments/$requestId/feedback" `
  -ContentType "application/json" -Body $feedbackBody
```

Keep the same request UUID when retrying transport or reading its recorded
outcome. Repeating the same body reuses the existing attempt, without another
model call. The UUID is bound to the original trace and reviewer; changing
either returns 409. A **new UUID explicitly requests another attempt**, even
when the question is unchanged. Attempts retain the configured model tag and
prompt/schema SHA-256 fingerprints; these are not immutable model digests.

Completed creation returns 200. A still-running duplicate returns 409.
Assessor/provider or proposal-validation failures are persisted and return 502;
invalid saved provenance returns 409. Both include the assessment ID for a
saved GET. Missing records return 404, database failures 503, and malformed
requests 422. GET returns the recorded state, including explicit failed
outcomes; failure is never converted into an evidence status such as `none`.

Feedback verdicts are `helpful`, `needs_correction`, and `unusable`. Corrections
and unusable assessments require nonblank notes plus unique reason codes:
`incorrect_status`, `request_omission`, `unsupported_claim`, `missing_condition`,
`irrelevant_fact`, `clarification_problem`, or `assessment_failed`.
Optional `corrected_status` requires `incorrect_status`. Failed attempts accept
only unusable feedback containing `assessment_failed`, without a status
correction; running attempts do not accept feedback. An identical feedback
retry returns the same event, while replacing feedback for the same reviewer
and assessment returns 409. Notes are limited to 2,000 characters.

Feedback does not approve, edit, reject, or deliver a draft, and is not
automatically promoted into evaluation gold. Exact quotes establish provenance,
not semantic entailment: inspect applicability, omitted requests, and conditions.
Reviewer identity remains caller-supplied; these are local workflow APIs, **not
authenticated reviewer-only access**. Do not expose them publicly as-is.

This is a synchronous, opt-in call, not a job queue. A crash or completion-write
outage can leave an attempt `running`; that state is not proof the worker is
alive. There is no automatic retry, lease expiry, or recovery worker. Inspect
the saved attempt and deliberately use a new UUID when another call is wanted.
There is no reviewer UI or trace-to-attempt listing endpoint yet; retain request
IDs in the client. See the [data model](docs/DATA-MODEL.md) and
[assessment boundary](docs/adr/008-claim-level-evidence-assessment.md).

## Step through a draft request in VS Code

Open the repository root in VS Code, then run the debug Compose profile in an
integrated terminal:

If a previous one-off `pdb` container is still running, it may reserve port
8000 even after Uvicorn has exited. Find it and stop only that container before
starting this profile:

```powershell
docker ps -a --filter "name=customer-support-copilot-api-run"
docker stop YOUR_CONTAINER_ID
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.debug.yml up --build api
```

The debug profile installs `debugpy` only in this development image, mounts
`services/api/app` from the workspace, and pauses API startup until VS Code
attaches. In **Run and Debug**, select **Attach to Support API (Docker)** and
press F5. Set breakpoints in `services/api/app/main.py` inside
`draft_support_reply`, and in `services/api/app/orchestrator.py` inside
`PreviewOnlyDraftOrchestrator.draft_reply`.

In a second terminal, send a request:

```powershell
$body = @{
  question = 'I forgot my password and cannot log in. How do I reset it?'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8000/v1/support/draft' `
  -ContentType 'application/json' `
  -Body $body
```

Use F10 to step over, F11 to step into, and Shift+F11 to step out. In the
debug console, inspect `payload.question` in the route, then `retrieval.hits`,
`retrieval.hits[0].text`, and `retrieval.hits[0].cosine_distance` in the
orchestrator. The cosine distance is raw retrieval metadata, not confidence.
The current preview-only path does not call an LLM.

Stop the debug Compose process with Ctrl+C. To return to the normal API image:

```powershell
docker compose up --build -d api
```

Week 3 ingestion uses `qwen3-embedding:0.6b` with 1024 dimensions. `POST /v1/ingestion/preview` only chunks and hashes content; it does not generate or store vectors. `POST /v1/ingestion/index` generates embeddings and stores them. A repeated `(source_key, policy_version)` with unchanged content is a no-op; content or policy metadata changes require a new `policy_version` so older evidence remains traceable.

## Next implementation steps

Start with [WEEK-01-EXECUTION-CHECKLIST.md](docs/WEEK-01-EXECUTION-CHECKLIST.md), then progress through ADR-backed decisions and eval-driven iterations.

Also review:
- [DOMAIN-SCOPE.md](docs/DOMAIN-SCOPE.md)
- [SUCCESS-CRITERIA.md](docs/SUCCESS-CRITERIA.md)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [DATA-MODEL.md](docs/DATA-MODEL.md)
- [adr/001-free-first-local-oss.md](docs/adr/001-free-first-local-oss.md)
- [adr/002-v1-domain-scope.md](docs/adr/002-v1-domain-scope.md)
- [adr/003-initial-data-model.md](docs/adr/003-initial-data-model.md)
- [adr/007-versioned-support-document-ingestion.md](docs/adr/007-versioned-support-document-ingestion.md)
- [adr/008-claim-level-evidence-assessment.md](docs/adr/008-claim-level-evidence-assessment.md)
