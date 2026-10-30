# ADR-013: React reviewer workbench with same-origin API access

Date: 2026-10-26
Status: Accepted

## Context

The learner selected React to learn frontend fundamentals through the existing
human-review workflow. The first slice must remain small, local, synthetic, and
review-first rather than introduce a second product or resume model tuning.

The learner approved this design and delegated implementation of W5-01 only.
Later question, evidence, and review integrations remain separate milestones.
Design approval does not establish that implementation or validation is done.
On 2026-10-30 the learner separately delegated W5-02 question-to-draft
integration. Evidence details and review actions remain deferred.

## Decision

- Use React, JavaScript, plain CSS, and Vite under `services/web/`.
- Start with one page, focused components, and local React state. Do not add
  TypeScript, routing, global state libraries, a UI kit, or SSR.
- During development, Vite proxies relative `/v1` requests to the existing
  FastAPI service. Do not add permissive CORS to compensate for development
  origins.
- Set the frontend base path to `/workbench/`. Vite produces
  `services/web/dist/`; do not commit generated assets or `node_modules`.
- Serve the built assets at `/workbench/` through FastAPI. Preserve existing
  API paths and their behavior. A missing build must produce an explicit
  unavailable response, not a placeholder that looks like the real workbench.
- Build frontend assets in a Node 24 Docker stage and copy them into the final
  Python image at `/web/dist/`, a sibling of the API's `/app/` directory.
  The API build context becomes the repository root, with a Docker ignore
  boundary excluding secrets and unrelated local files.
- Run only Python/Uvicorn in the final application container. Nginx, a Node
  production server, public hosting, and independent frontend deployment are
  not part of this slice.

## API contract

Reuse the contracts in [schemas.py](../../services/api/app/schemas.py) and the
existing [routes](../../services/api/app/main.py):

| Action | Input | Important behavior |
|---|---|---|
| Draft | `POST /v1/support/draft` with `question` of 5-3,000 characters | Returns a persisted draft trace, mode, review state, evidence/citations, and available assessment/check metadata. Optional ticket/tier inputs are not needed for the first UI slice. |
| Review | `POST /v1/support/review` with `trace_id`, `reviewer_id`, and `status` | `edit` requires nonblank text up to 5,000 characters; `reject` requires an existing reason code. The backend owns the final transition and audit record. |

Preview-only notices cannot be approved unchanged. A pending draft can receive
only one final review decision. Reviewer identity is caller-supplied and is not
authentication. See [ADR-009](./009-persisted-support-review-lifecycle.md).

Do not call simulated delivery or any customer-sending integration.

## UI responsibilities and states

- The page owns the active question, returned draft trace, request states,
  and server-confirmed review result.
- Focused question, draft/evidence, and review components receive the data and
  actions they need. Review input belongs to the active trace; never apply an
  old edit or review response to a different draft.
- Start with initial, draft-submitting, draft-available, review-submitting,
  review-confirmed, and explicit error/unconfirmed states.
- Treat preview-only and abstention outcomes as distinct content states, not
  as successful generated answers or generic transport errors.
- Display unknown confidence as unknown and returned checks as checks, not
  semantic proof. Keep failed-check drafts visible for human correction.
- Trigger draft/review writes from explicit actions, never render or mount
  effects. Prevent conflicting submissions; do not automatically retry POSTs.
- Preserve the question and unsaved edit in memory after errors. This is not
  durable autosave and does not promise survival across a page reload.
- If a review response is lost, its outcome is unconfirmed: the server may
  have committed before the connection failed. Do not claim either success or
  definite non-persistence.
- Render external text as React text content, not executable HTML.

W5-01 provides only the accessible shell. Its action buttons stay disabled
with an explanation; it performs no support API requests.

### W5-02 implementation clarification

- The parent owns a single request-state object and the response's submitted
  question. Keep the question and submit control disabled in flight; an
  immediate ref guard also blocks duplicate events before the next render.
- Editing the question after a response does not relabel that response. Starting
  a new request clears the old result and trace. Review actions remain disabled.
- A small fetch helper validates input and the core/displayed response fields,
  reports HTTP/network/JSON errors, and preserves optional/unknown metadata
  without inventing a passing check. This is not a duplicate backend policy
  engine or a complete client implementation of every response schema.
- Do not add a fixed client inference deadline or cancellation control in this
  slice. Await the response/network outcome, preserve input on error, and warn
  that an unconfirmed response may still correspond to a saved draft. Reloading
  is not guaranteed to cancel backend work or retain browser state.
- Use Node's built-in test runner for the request helper, existing lint/build
  checks, and controlled browser checks. No extra dependency is required.

## Options Considered

1. Vanilla JavaScript served by FastAPI: smallest toolchain, but does not meet
   the learner's chosen React learning goal.
2. React/Vite source with FastAPI-served assets: selected; adds a build step
   without adding another production service.
3. Independently hosted React or an SSR framework: useful for other deployment
   or initial-render requirements, but not justified by this local slice.

## Tradeoffs

- Benefits: a clear UI/API boundary, component/state learning, same-origin
  browser requests, and reuse of the established review lifecycle.
- Costs: a Node/npm build toolchain and frontend asset integration in the API
  image; UI and API releases remain coupled.
- Risks: stale trace/input associations, duplicate writes, misleading check
  labels, lost unsaved edits on reload, and build/runtime asset-path mismatch.
  The planned states and focused validation address these explicitly.

## Rollback Trigger

Revisit separate static hosting when independent releases, CDN delivery, or
asset traffic requirements justify it. Revisit routing, shared state, or SSR
only for demonstrated requirements. A UI rollback must leave API behavior
intact and must not enable automation.

## Validation Metrics

- Frontend lint and production build pass.
- The built UI and assets load under `/workbench/` in development and from the
  API image; existing API paths are not shadowed.
- Missing build and unknown asset paths fail explicitly; static serving does
  not expose files outside the build directory.
- Focused backend tests and a browser walkthrough cover the shell and
  existing API routing. W5-01 makes no support API POSTs.
- Subsequent integration milestones verify normal, preview, abstention,
  conflict, and error paths without delivery calls or automation.

No quality, latency, public-deployment, or production-readiness gate is passed
by this decision. See the [Week 5 checklist](../WEEK-05-EXECUTION-CHECKLIST.md).
