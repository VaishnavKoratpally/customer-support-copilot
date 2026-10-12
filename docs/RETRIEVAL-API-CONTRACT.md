# Retrieval API Contract v1

## Endpoint
`POST /v1/retrieval/query`

## Request
```json
{
  "question": "I was charged twice for my plan. Can you help?",
  "top_k": 3
}
```

## Response
```json
{
  "query": "I forgot my password and cannot log in.",
  "top_k": 3,
  "hits": [
    {
      "rank": 1,
      "chunk_id": "11111111-1111-4111-8111-111111111111",
      "source_id": "account-recovery-01",
      "title": "Account recovery policy",
      "policy_version": "v1",
      "effective_date": "2026-10-06",
      "access_scope": "internal",
      "chunk_index": 0,
      "section_path": "Account recovery",
      "excerpt": "Customers can start a password reset from the sign-in page.",
      "cosine_distance": 0.18
    }
  ]
}
```

`cosine_distance` is the raw pgvector cosine distance. Lower values mean closer
vectors; it is not a confidence score and does not establish that the returned
chunks are sufficient evidence.

The endpoint embeds the question with the configured embedding model and uses
exact cosine search. It selects the latest policy version effective today or
earlier, then searches `public` and `internal` sources. `restricted` sources are
excluded. If the newest effective date is ambiguous for an in-scope source, or
the stored model/digest does not match the query embedding, the endpoint returns
an error instead of silently selecting incompatible evidence.

The access-scope filter is a local support-agent behavior, not caller
authorization. This route returns nearest candidates even when the corpus may
not contain an answer; it does not apply a distance cutoff or make an
evidence-sufficiency decision.

`POST /v1/support/draft` uses the same pgvector retriever in `preview_only`
mode. It returns each retrieved chunk as a citation, including source/version
metadata and raw cosine distance. The distance is diagnostic only: it is not
converted into confidence or used as an answerability threshold. If no eligible
chunks are returned, the endpoint reports that explicitly. In both cases it
generates no customer answer, leaves confidence fields null, and requires
human review. It does not fall back to static stub evidence. See
[ADR-011](./adr/011-preview-only-draft-retrieval.md) for the reason generation
remains disabled.