# Chunking Policy v1 (Day 3)

## Goal
Produce semantically coherent, deterministic chunks for retrieval with traceable metadata.

## Strategy
- Split source docs by heading/section first.
- Within each section, chunk by approximate token length.
- Preserve sentence boundaries when possible.

## v1 Parameters
- target_chunk_tokens: 450
- chunk_overlap_tokens: 75
- min_chunk_tokens: 120
- max_chunk_tokens: 700

## Rules
1. Never merge content across major section headers.
2. Preserve list structure and numbered steps inside a chunk.
3. If a section is smaller than min_chunk_tokens, merge with nearest sibling section only if topic matches.
4. If a section exceeds max_chunk_tokens, split on paragraph boundaries, then sentence boundaries.
5. Every chunk must map to one source document and one section path.

## Required metadata per chunk
- document_id
- source_key
- title
- doc_type
- product_area
- policy_version
- effective_date
- access_scope
- section_path
- chunk_index
- token_estimate
- checksum_sha256

## Why these defaults
- 450/75 balances retrieval precision and context continuity for support policy text.
- Deterministic boundaries improve reproducibility of eval results.

## Future tuning triggers
Tune chunk parameters when:
- Recall@5 < 0.75
- citation correctness drops below 0.95
- retrieval latency exceeds target under expected corpus size