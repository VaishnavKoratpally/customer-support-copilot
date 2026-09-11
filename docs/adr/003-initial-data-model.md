# ADR-003: Initial data model for support + RAG traceability

Date: 2026-09-11  
Status: Accepted

## Context

The platform needs a schema that supports both:

- deterministic support workflows (tickets, messages, reviews),
- AI answer traceability (document source, chunks, and audit actions).

## Decision

Adopt a unified Postgres schema with:

- operational tables: `tickets`, `conversation_messages`, `audit_events`
- knowledge tables: `source_documents`, `document_chunks`
- pgvector extension for in-database vector search

## Options Considered

1. Separate OLTP DB and vector DB from day 1
2. Unified Postgres + pgvector for v1
3. Document store + external vector DB

## Tradeoffs

- Benefits:
  - simpler operations and fewer moving pieces in v1
  - direct joins between support and knowledge metadata
  - easier local development
- Costs:
  - vector search performance headroom lower than specialized stores at high scale
  - careful index tuning required as corpus grows
- Risks:
  - embedding dimension coupling requires migration discipline
  - potential write/read contention at larger workloads

## Rollback Trigger

If retrieval latency or recall degrades under realistic load, migrate vector workload to Qdrant while preserving the retriever interface contract.

## Validation Metrics

- retrieval P95 latency <= 300ms at target corpus size
- Recall@5 >= 0.75 on retrieval eval set
- audit completeness for reviewed answers = 100%

