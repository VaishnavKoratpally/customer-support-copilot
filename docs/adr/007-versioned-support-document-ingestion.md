# ADR-007: Versioned support-document ingestion

Date: 2026-10-06  
Status: Accepted

## Context

Support answers must be traceable to the policy version that supplied their evidence. Replacing a document by `source_key` alone would erase prior policy text and make later audits ambiguous. The Week 3 corpus is also very small, so approximate nearest-neighbor indexing would add tuning and recall tradeoffs before there is a measured performance need.

## Decision

- Identify a policy source version by `(source_key, policy_version)`.
- Treat source content and policy metadata as immutable within a version. Re-ingesting the same version is idempotent; changing its content or policy metadata returns a conflict and requires a new `policy_version`.
- Store new policy versions alongside older versions.
- Use deterministic IDs for source versions and chunks.
- Treat embeddings as derived data. Record the embedding model name, Ollama digest, dimension, and chunker configuration. If that configuration changes, atomically replace the vectors for the same immutable source version.
- Use exact pgvector cosine-distance search for the Week 3 corpus. Do not create an approximate index until corpus-scale measurements justify one.
- Keep `/v1/ingestion/preview` read-only. Use `/v1/ingestion/index` to generate and persist vectors.

## Options considered

1. **Overwrite one row per `source_key`.** Simpler and uses less storage, but destroys policy history.
2. **Preserve each `(source_key, policy_version)`.** Chosen; supports traceability at the cost of more rows and requires retrieval to select the applicable version.
3. **Create an approximate vector index immediately.** Rejected for this eight-chunk seed corpus; the index would be premature and its recall/latency tradeoff would not yet be measurable.

## Consequences and tradeoffs

- Old policy content remains available for audit and historical retrieval.
- Retrieval must filter or select versions using effective dates and access scope; retaining old versions must not make obsolete or future-dated policies eligible by default.
- A model or chunker change requires re-embedding. The current design replaces derived chunks atomically and does not retain previous embedding generations; exact historical retrieval replay would require immutable index generations.
- The fixed `vector(1024)` dimension couples model configuration to a database migration. Any dimension change must migrate the vector column and re-embed the corpus rather than mix dimensions.
- Exact search keeps the small initial corpus simple and avoids approximate-index recall loss. Revisit after measuring retrieval latency and recall at the target corpus size.

## Failure behavior

- A changed source under the same policy version is rejected with HTTP 409.
- Ollama failures or invalid vector output fail indexing with HTTP 502; vectors are never stored on a failed embedding request.
- PostgreSQL failures fail indexing with HTTP 503. Source metadata and replacement chunks are written in one transaction.

## Revisit triggers

- Add immutable embedding/index generations if audit requirements need exact retrieval replay across model or chunker upgrades.
- Consider HNSW or IVFFlat only if measured exact-search latency exceeds the retrieval SLO at a representative corpus size; compare recall as well as latency.
- Add retention rules only after defining the audit and legal requirements for historical policy versions.

## Validation evidence

- The three synthetic Week 3 documents were indexed as eight 1024-dimensional vectors with the selected Ollama model digest.
- Re-ingestion returned `unchanged` without generating vectors again.
- A same-version content change returned HTTP 409; a new policy version was stored alongside the old version.
- Changing and restoring chunk configuration reindexed atomically while preserving the source-version ID.
