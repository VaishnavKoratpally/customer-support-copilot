# ADR-011: Preview-only real retrieval in the draft path

## Status

Accepted

## Context

The `/v1/retrieval/query` endpoint already embeds questions and searches the
versioned pgvector corpus. `/v1/support/draft` still used a static retriever,
so its evidence and citations did not represent the indexed support content.

Raw cosine distance is not a calibrated confidence score or an answerability
decision. The standalone evidence assessor has also produced incorrect
schema-valid outputs on the current small local model and has timed out on
larger local models. ADR-008 therefore prohibits using that assessor to
authorize generated answers until its labeled evaluation gate passes.

## Decision

- Wire the real pgvector retriever into `/v1/support/draft`, using the same
  embedding and index configuration as `/v1/retrieval/query`.
- Return retrieved chunks as citations, including source, version, effective
  date, access scope, chunk identity, section, and raw cosine distance.
- Treat distance as diagnostic metadata only. Do not derive retrieval or answer
  confidence from it; persist and return both confidence values as `NULL`.
- Do not call an LLM or the evidence assessor. Return a deterministic
  preview-only abstention notice, with a distinct message for no retrieved
  evidence, and put every preview in `pending_review`.
- Do not fall back to static evidence if embedding or retrieval fails. Return
  the relevant service error.
- A preview notice cannot be approved unchanged or delivered. A human must
  edit it into a customer response before simulated delivery is allowed.
- Keep generated-answer quality evaluators disabled for preview responses so
  deterministic notices cannot produce misleading quality scores.

## Consequences

Agents can inspect actual indexed evidence and its provenance while the
evidence-sufficiency mechanism remains unvalidated. The endpoint is not yet a
customer-answer generator, and the existing confidence thresholds are not
meaningful in this mode.

The preview flow adds a persisted `draft_mode` and allows confidence columns to
be null. Existing rows default to `generated`; the migration preserves their
current behavior. Generated answers may be enabled only after the fixed
evidence-assessment set meets ADR-008's no-false-sufficient acceptance gate.
