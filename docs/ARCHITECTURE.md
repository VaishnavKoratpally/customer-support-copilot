# Architecture v0 (Week 1)

## Goal

Ship a support copilot architecture that is understandable, testable, and safely operable before adding advanced AI capabilities.

## High-level flow

1. User submits support question
2. Router classifies intent and risk
3. Retriever fetches evidence chunks
4. Main model drafts an answer with citations
5. Confidence policy decides whether human approval is required
6. Human agent reviews/edits/approves when required
7. System logs events, traces, and evaluation telemetry

## Service boundaries

- **API service (FastAPI)**  
  Orchestrates request flow, risk routing, retrieval, model calls, and HITL policy checks.

- **PostgreSQL (+pgvector)**  
  Stores tickets, conversation events, audit logs, and vector embeddings.

- **Redis**  
  Ephemeral caching and queue-ready primitives for future async tasks.

- **Ollama**  
  Local model serving for router/main/escalation LLMs and embeddings.

## Core design choices

### 1) Provider abstraction
- Keep `LLMProvider`, `Retriever`, and evaluation interfaces decoupled.
- Enables local-first now and hybrid provider benchmarking later.

### 2) Bounded model routing
- `qwen3:4b` for intent/risk routing
- `qwen3:14b` as default answer model
- `qwen3:20b` only on low-confidence/high-impact paths

### 3) Human-in-the-loop by policy
- High-risk intents always require human approval
- Low answer confidence requires human approval
- Missing citations require human approval

### 4) Evidence-preserving outputs
Every answer payload must include:
- citations
- confidence score
- escalation reason (when applicable)

## Immediate risks and mitigations

- **Risk**: slow local inference on limited hardware  
  **Mitigation**: escalation model used only for hard cases; enforce latency SLOs.

- **Risk**: retrieval misses crucial policy docs  
  **Mitigation**: track Recall@k and add regression tests for known queries.

- **Risk**: unsafe auto-send behavior  
  **Mitigation**: mandatory HITL gates for high-risk intents and low confidence.

