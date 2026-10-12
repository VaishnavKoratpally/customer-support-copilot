# Customer Support Copilot (Human-in-the-Loop)

This repository is the implementation workspace for a production-grade, free-first customer support copilot. The design prioritizes:

- local OSS models first (Ollama)
- explicit human-in-the-loop guardrails
- measurable quality via evaluation harnesses
- architecture decisions documented with tradeoffs

## Learning and collaboration approach

This is also a deep-learning project in AI engineering and system design. See [Learning and Engineering Contract](docs/LEARNING-CONTRACT.md) for the guide-first workflow, scale assumptions, debugging practice, and expectations for using AI effectively.

## Current milestone

Week 1 baseline scaffold:

- local runtime stack (Postgres + Redis + Ollama + API) via Docker Compose
- API skeleton with routing, retrieval, confidence policy, and HITL decisioning
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

3) Initialize the database. The fresh schema includes the current tables and review lifecycle. When upgrading an existing Week 2 database, apply migrations in order before starting the API:

```powershell
# Fresh database
Get-Content .\services\api\db\schema.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot

# Existing Week 2 database (apply migrations in order; skip those already applied)
Get-Content .\services\api\db\migrations\001_week3_versioned_embeddings.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\002_persisted_support_review_lifecycle.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
Get-Content .\services\api\db\migrations\003_simulated_support_delivery.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U support_user -d support_copilot
```

If migrations `001` and `002` were already applied, run only `003`.

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

When the draft response says `not_required`, or the review response says `approved` or `edited`, use its trace ID to create a local simulated-delivery receipt:

```powershell
curl -X POST http://localhost:8000/v1/support/simulated-deliveries `
  -H "Content-Type: application/json" `
  -d "{\"trace_id\":\"YOUR_TRACE_ID\"}"
```

This records a hash-only receipt; it does not send a message to a customer or external service. Pending or rejected drafts are refused.

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
