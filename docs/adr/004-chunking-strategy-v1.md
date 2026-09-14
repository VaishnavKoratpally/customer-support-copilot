# ADR-004: Chunking strategy v1

Date: 2026-09-14
Status: Accepted

## Context
RAG quality depends strongly on chunk boundaries and metadata quality. We need a deterministic baseline before ingestion implementation.

## Decision
Adopt heading-aware, token-targeted chunking with sentence/paragraph boundary preference.
Defaults: target 450 tokens, overlap 75, min 120, max 700.

## Options Considered
1. Fixed-size character chunking
2. Heading-aware token chunking (chosen)
3. Semantic model-based chunking

## Tradeoffs
- Benefits:
  - better semantic coherence than fixed-size chunks
  - deterministic behavior for eval reproducibility
- Costs:
  - moderate implementation complexity
- Risks:
  - may underperform on highly unstructured documents

## Rollback Trigger
If retrieval metrics stagnate after prompt and retriever tuning, test semantic chunking and compare on same eval suite.

## Validation Metrics
- Recall@5 >= 0.75
- Citation correctness >= 0.95
- Retrieval P95 latency within target