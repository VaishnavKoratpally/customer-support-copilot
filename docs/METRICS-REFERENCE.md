# Metrics Reference (Day 6)

## Purpose

Define baseline service metrics for local observability so we can quickly answer:

- Are requests succeeding?
- How fast are requests?
- How often are support drafts escalated to human review?

## Endpoint

`GET /v1/metrics`

Returns a JSON snapshot of in-memory counters and latency summaries.

---

## Metric fields

### Request-level metrics

- `request_total`  
  Total number of HTTP requests observed by API middleware.

- `request_error_total`  
  Count of requests with HTTP status `>= 500`.

- `request_error_rate`  
  `request_error_total / request_total`  
  Signals stability and server-side reliability issues.

- `request_latency_p50_ms`  
  50th percentile request latency in milliseconds (median-ish experience).

- `request_latency_p95_ms`  
  95th percentile request latency in milliseconds (tail latency / worst-case trend).

### Support workflow metrics

- `support_draft_total`  
  Number of `/v1/support/draft` responses emitted.

- `support_human_review_total`  
  Number of support drafts that required human review.

- `support_human_review_rate`  
  `support_human_review_total / support_draft_total`  
  Proxy for escalation pressure and draft confidence behavior.

---

## Example response

```json
{
  "request_total": 42,
  "request_error_total": 1,
  "request_error_rate": 0.0238,
  "request_latency_p50_ms": 18.41,
  "request_latency_p95_ms": 75.92,
  "support_draft_total": 12,
  "support_human_review_total": 7,
  "support_human_review_rate": 0.5833
}