# Week 5: Local React Human-Review Workbench

Date: 2026-10-16
Updated: 2026-10-26
Status: W5-00 design approved and recorded in ADR-013; learner walkthrough pending. W5-01 shell implemented and validated. W5-02 onward is not started or authorized under this slice.

## Why this milestone

The learner wants to build and understand the system rather than spend the next
milestone tuning promotion gates. A small reviewer workbench makes the existing
RAG and human-review flow tangible while keeping AI engineering as the main
focus.

This deliberately moves only a first, local UI slice forward. The original
roadmap places the broader human-in-the-loop UI in Weeks 6-7. This milestone
does not complete Week 4, pass its quality or latency gates, or authorize
automation.

## Objective

Build a small React browser workbench for a single local reviewer using the
existing draft and review APIs. Learn JavaScript fundamentals alongside React
components, props, controlled forms, and state while making the draft, evidence,
checks, and persisted human decision visible. Frontend learning supports the AI
workflow; it does not become a separate product or a prerequisite to more model
tuning.

The learner should be able to explain the browser-to-API request flow, the
server-owned decision state, the main tradeoffs, and how errors are presented.

## Assumptions and constraints

- One local reviewer; one draft/review interaction at a time.
- Synthetic support questions and sources only. No real customer data.
- Existing FastAPI, retrieval, draft, and review behavior is authoritative.
- Generated drafts remain review-first. Automation stays disabled.
- Local free-first development. React and Vite with JavaScript are selected
  for development and builds. Node.js/npm are development/build requirements,
  not a new production application service.
- Keep dependencies minimal. Additional UI, state-management, routing, or test
  libraries need a demonstrated requirement and learner approval.
- No new latency target or model-quality claim. Existing Week 4 measurements
  remain unchanged.
- This is a local learning milestone, not a production-readiness claim.

## Approved design

Use React with semantic HTML, plain CSS, and JavaScript ES modules. Use a
minimal Vite application under `services/web/`, separate from the Python API
source. Keep one page with a few focused components and local React state; no
router or global state library is needed for this slice.

Approved development and serving boundary:

- **Development:** Vite serves the React page and proxies relative `/v1`
  requests to FastAPI. The browser calls its own UI origin; the proxy forwards
  API requests to the backend without requiring permissive CORS.
- **Built application:** Vite produces static assets. FastAPI serves them under
  an agreed workbench path on the API origin. Configure Vite's asset base for
  that path; do not mount the UI over existing API routes.
- Use relative `/v1/...` URLs in the browser in both modes. Node.js is needed
  to develop/build the UI, not to serve its built assets.
- Build to `services/web/dist/` and copy assets into `/web/dist/` in the final
  API image using a Node 24 build stage. Keep generated assets reproducible
  rather than manually copying or committing build output.
- Use a repository-root Docker build context with an explicit ignore boundary.
  Keep the final container Python/Uvicorn-only.

The learner approved this design and delegated W5-01 only on 2026-10-26.
[ADR-013](./adr/013-react-reviewer-workbench.md) records the contract,
state ownership, failure behavior, tradeoffs, and revisit triggers.

The request flow remains:

1. The reviewer enters a synthetic support question.
2. The browser sends it to `POST /v1/support/draft`.
3. The page displays the response as returned by the API: draft state and text,
   evidence/citations, and any assessment or final-check information present.
4. The reviewer edits, approves, or rejects using `POST /v1/support/review`,
   subject to the API's current contract and allowed transitions.
5. The page displays the server-confirmed review result.

Before implementation, inspect the current request/response schemas and
transition rules. Do not infer a pass from missing fields, invent confidence,
or treat citation presence as proof that a claim is supported.

### Tradeoffs

| Option | Benefits | Costs | Decision |
|---|---|---|---|
| FastAPI-served vanilla JavaScript | Fewest dependencies; teaches browser fundamentals without a build step | Manual DOM/state coordination; does not meet the learner's chosen React learning goal | Replaced by React at the learner's request |
| React/Vite source with FastAPI-served build | Teaches components and state while preserving the existing API boundary; no separate production frontend service | Adds Node/npm, a build step, and development proxy configuration; UI and API still deploy together | Accepted in ADR-013 |
| Independently deployed React frontend | Independent frontend releases and hosting | Adds another deployment boundary and proxy/CORS configuration | Defer until independent deployment is a demonstrated requirement |

Keep React responsible for presentation and transient interaction state.
FastAPI remains authoritative for validation, risk/check results, review
transitions, and persistence. Do not duplicate those policies in the browser.

## In scope

- A single workbench page with a question form, clear loading/empty/error states,
  and an evidence/review area.
- Display the draft and response metadata the API actually returns, including
  citations/evidence and applicable assessment or final-check results.
- An editable final-draft field and review actions supported by the existing
  API. Show the persisted result, not an optimistic success message.
- Basic keyboard accessibility, labels, focus behavior, and readable status
  messages.
- Minimal React/Vite scaffolding, development proxy, reproducible static build,
  and FastAPI/container integration for serving that build.
- Focused frontend lint/build checks and tests for static serving and relevant
  client/API behavior, plus a documented manual browser walkthrough.

## Out of scope

- TypeScript migration, Next.js/server-side rendering, React Router, Redux,
  component libraries, or a separate production frontend service.
- Changes to prompts, models, embeddings, retrieval, assessment, evaluation
  gates, thresholds, or latency targets.
- Simulated delivery, real customer sending, automatic approval, or automation.
- Authentication, multi-tenancy, a reviewer queue, public hosting, or real
  customer data.
- Resolving the Week 3/4 quality or latency NO-GOs as part of the UI work.

## Failure behavior and safety

| Situation | Required behavior |
|---|---|
| API, model, or database error | Show a clear error; preserve the question and any unsaved edit; do not show a fabricated draft or success-shaped fallback. |
| Preview-only, abstention, or no-evidence response | Display the actual state and available evidence. Do not invent an answer or imply that a draft passed checks. |
| Review validation, conflict, or server error | Show that the decision was not confirmed; preserve the user's text; do not automatically retry or claim the review was saved. |
| Optional or unknown response fields | Represent missing/unknown information as such; never substitute a positive check or confidence value. |
| API-provided text | Render as React text content, not executable HTML; do not use `dangerouslySetInnerHTML`. |
| Repeat submission while a request is active | Prevent accidental double-submit in the UI and handle server errors explicitly; do not add silent retry behavior. |
| React rendering or development effect replays | Trigger draft/review POST requests only from explicit user actions, not render or mount effects; rerendering must not create writes. |

Application API calls from the browser must use only the draft and review
endpoints for this milestone. Static assets and Vite development traffic are
separate from these API calls. The page must not call
`/v1/support/simulated-deliveries`.

## Learning sequence

1. Review the existing API schemas and draw the request/response flow before
   writing UI code.
2. Learn the small set of HTML/CSS and browser JavaScript concepts needed for
   the page: forms, modules, events, `fetch`, promises, and accessible status
   updates.
3. Learn React components, props, controlled inputs, local state, and event
   handlers. Distinguish a UI rerender from an API request; avoid effects for
   user-triggered POST operations.
4. Learn only the Vite/npm setup needed to run, lint, build, and proxy API
   requests; defer unrelated frontend tooling.
5. Implement one visible state at a time: initial, submitting, draft ready,
   review submitting, review complete, and error.
6. Walk through one successful human-review path and one failure path; explain
   what the server owns versus what the browser only displays.

References:

- [React: Quick Start](https://react.dev/learn)
- [React: Managing State](https://react.dev/learn/managing-state)
- [Vite: Getting Started](https://vite.dev/guide/)
- [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/)
- [MDN: JavaScript modules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules)
- [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [MDN: HTML forms](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms)

## Checklist tasks

Check tasks only when evidence exists. W5-00 design approval authorizes
W5-01, not an unattended implementation of the entire week. Record the learner
walkthrough separately from approval and from implementation evidence.

### W5-00: Confirm the contract and approve the design

- [x] Inspect the current draft/review request and response schemas and allowed
  review transitions.
- [x] Agree on the page states for draft, preview-only, no-evidence,
  submitting-review, review-complete, and API/validation errors.
- [x] Review the selected React direction and approve the proposed Vite/
  JavaScript setup, development proxy, built-asset path, and container build
  integration before implementation.
- [x] Agree on minimal component responsibilities, UI state ownership, and
  acceptance checks; keep backend decisions authoritative.
- [x] Record the agreed frontend boundary, alternatives, consequences, and
  revisit triggers in an ADR.
- [ ] Complete the learner walkthrough of the API flow, allowed review
  transitions, and ambiguous review-response failure before claiming the full
  W5-00 learning exit.

Exit evidence: the learner can explain the API flow and approves the
request/response fields, allowed actions, failure behavior, and validation
plan.

### W5-01: Create the React workbench shell

- [x] Scaffold the approved minimal React/Vite JavaScript application under
  `services/web/` using the package manager/scaffolding tool; retain its
  dependency lockfile.
- [x] Build an accessible single-page shell with focused components and plain
  CSS; do not add routing, global state, or a component library.
- [x] Configure relative API calls through the Vite development proxy.
- [x] Configure the Vite asset base and FastAPI static mount for the agreed
  workbench path without shadowing API routes.
- [x] Wire a reproducible frontend build into the API image build; serve only
  the generated static assets at runtime, without a Node production server.
- [x] Document Node/npm prerequisites and local dev, lint, build, and
  container-start commands.
- [x] Verify the page loads in both Vite development mode and the
  FastAPI-served build without permissive CORS.

### W5-02: Implement the question-to-draft flow

- [ ] Add a labeled controlled question form and explicit React state for
  initial, submitting, ready, and error conditions.
- [ ] Call the existing `POST /v1/support/draft` endpoint using `fetch` from an
  explicit submit handler; handle non-2xx responses as errors.
- [ ] Disable conflicting submissions while a request is active and bind
  subsequent review actions to the returned draft's trace ID.
- [ ] Render the returned draft and status without assuming optional fields
  exist or treating unknown values as success.
- [ ] On failure, show a visible error and preserve the question; do not show a
  fabricated draft or silently retry.

### W5-03: Show evidence and final checks

- [ ] Display returned citations/evidence and provenance in focused React
  components with stable keys derived from the API contract.
- [ ] Display assessment, risk, review-trigger, or final-check fields when
  returned by the API.
- [ ] Represent missing/unknown information as unknown; do not infer
  entailment, confidence, or a passing check from citation presence.
- [ ] Render API-provided text as React text content, not executable HTML.

### W5-04: Implement human review actions

- [ ] Add a controlled final-draft field and only the review actions supported
  by the existing API contract; keep review state bound to the current trace.
- [ ] Collect any required rejection reason or other required review input.
- [ ] Call the existing `POST /v1/support/review` endpoint from an explicit
  action handler and show the server-confirmed result.
- [ ] Preserve unsaved text and report validation, conflict, timeout, or API
  errors without claiming the decision was saved.
- [ ] Do not call `/v1/support/simulated-deliveries` or any external sending
  service.

### W5-05: Verify the workbench

- [ ] Run the frontend scaffold's lint command and production build; record
  results.
- [ ] Add focused tests for built-asset serving, preservation of API routes,
  and any changed API-facing behavior.
- [ ] Verify Vite-proxied and FastAPI-served API calls, including explicit error
  responses and asset loading under the configured workbench path.
- [ ] Manually verify a normal draft/review flow and the preview-only and
  no-evidence states.
- [ ] Manually verify API-unavailable and review-error behavior, including
  preservation of user input and absence of automatic retries.
- [ ] Check keyboard operation, labels, focus, and readable status/error
  messages.
- [ ] Verify rerendering or React development checks do not create duplicate
  POST requests; active-request controls prevent accidental double-submit.
- [ ] Confirm in the browser network log that application API calls used only
  draft and review endpoints; no delivery request occurred.

### W5-06: Complete the learning review

- [ ] Walk through the browser-to-API data flow, state transitions, and
  development-proxy versus built-same-origin tradeoff.
- [ ] Explain React components, props, controlled form state, and why writes
  belong in explicit event handlers rather than render or mount effects.
- [ ] Explain what the UI trusts from the server and how it handles errors.
- [ ] Record commands, results, unresolved issues, and the learner's
  understanding before marking tasks complete.
- [ ] Confirm Week 3 and Week 4 carryovers below remain accurately tracked;
  do not mark their gates passed because the workbench exists.

Completion rule: check a task only after its stated evidence exists. Code
existing by itself is not completion evidence.

## Progress evidence

| Date | Task | Evidence/result |
|---|---|---|
| 2026-10-26 | W5-00 design | Inspected current draft/review schemas, routes, rejection taxonomy, review workflow, and persisted preview/transition guards. Learner explicitly approved the proposed design and delegated W5-01 shell implementation. ADR-013 records the decision. The final learner walkthrough is not yet recorded. |
| 2026-10-26 | W5-01 initial prerequisites | `Get-Command node.exe, npm.cmd` failed because `node.exe` was not available on this command environment's PATH. Docker client 29.7.2 initially could not connect to `dockerDesktopLinuxEngine`. At this point no scaffold, dependency installation, build, or validation pass had occurred. |
| 2026-10-26 | W5-01 toolchain recovery | Learner started Docker Desktop. A temporary official Node container provided Node 24.22.1 and npm 11.19.1; `create-vite` 9.3.1 scaffolded the React JavaScript/ESLint template with immediate installation/server startup disabled. Initial image downloads hit TLS transport errors and the first npm install timed out. Standard retries and a temporary npm cache with bounded download concurrency succeeded; TLS verification was never disabled. No native Node installation was made. |
| 2026-10-26 | W5-01 frontend | Added controlled question input and character count, separate draft/evidence/review panels, visible unknown/empty states, and disabled API actions. `npm run lint` and `npm run build` passed using the Node container; Vite 8.3.5 produced the ignored `services/web/dist/` build. The npm-generated lockfile is retained. No UI API integration or simulated delivery was implemented. |
| 2026-10-26 | W5-01 backend regressions | API venv Python 3.12.10: `python -m unittest tests.test_workbench tests.test_support_draft_preview tests.test_support_review_api` from `services/api` passed 20 tests. Nine new static-serving tests cover index/JS delivery, slash redirect, unknown assets, outside-directory refusal, missing/partial builds, explicit unavailable logging, and API-route preservation. The editor test tool did not discover these files; the repository's standard unittest invocation supplied the execution evidence. |
| 2026-10-26 | W5-01 image and proxy | Base and debug `docker compose config --quiet` checks passed. A repository-root Docker build restored frontend dependencies with `npm ci` and built the combined image. Its isolated runtime returned HTTP 200 for `/health`, the workbench, and base-prefixed JS/CSS. Vite forwarded `/v1/metrics` and preserved a backend 404. Runtime assertions confirmed built assets at `/web/dist/`, no Node/npm executable, and no copied `/app/.env`. The draft-request counter stayed zero. Debug configuration merging was checked; an attached debugger session was not run. |
| 2026-10-26 | W5-01 browser | Integrated-browser checks passed for Docker-backed Vite development and the packaged FastAPI-served UI. Verified controlled character counts, all four action buttons disabled, skip-link/main/question keyboard focus, desktop two-column layout, and a single column at 390px without horizontal overflow. Browser resource timing confirmed packaged JS/CSS and no UI `/v1` requests; visual inspection confirmed readable shell/status/focus presentation. Native Windows Node development was not executed. |
| 2026-10-26 | W5-01 cleanup and boundary | Stopped and removed only the task-owned validation containers, temporary npm-cache volume, and isolated test image tag. Source, lockfile, and ignored local build/dependencies remain; existing infrastructure was not stopped. No real draft/review request, model inference, simulated delivery, automation enablement, staging, or commit was performed. W5-02 onward and the learner walkthrough remain open. |

## Acceptance criteria

- The React workbench uses the existing API contracts through relative URLs.
  Development uses the Vite proxy; built assets load from the API origin under
  the agreed path without shadowing API routes.
- Frontend lint and production build succeed. The container build includes the
  UI assets reproducibly; no Node production server is required.
- The page shows API-returned draft state, evidence/citations, and checks
  without implying that citations alone prove semantic support.
- Review actions respect server-enforced transitions. The UI reports the
  server's persisted result and does not claim an unconfirmed action succeeded.
- API errors are visible and do not erase the user's question or unsaved edit.
- The browser makes no simulated-delivery or external customer-send request.
- Focused validation covers built-asset serving and the manual browser paths,
  including duplicate-submit and rerender checks. Any additional test tooling
  requires a separate justification and learner approval.
- The learner can explain what this local slice does not establish: quality
  promotion, latency compliance, security/auth readiness, or production scale.

## Week 3 and Week 4 carry-over

This milestone does not silently close earlier work:

- **Week 3:** The retrieval/indexing preview, fixed evaluation contract, and
  safe no-evidence preview are recorded complete. The RAG/evaluation and
  Ollama/pgvector readings remain unchecked. The generated-response quality
  and sufficiency exit is not a pass. The historical Week 2 20/20 review
  reasons cannot be reconstructed. The controlled model-size comparison is
  deferred as `PERF-01`.
- **Week 4:** W4-01 through W4-03 are complete. W4-04 has a quality NO-GO;
  W4-05a/b have a latency NO-GO on p50, with p95 passing; W4-05c automation is
  blocked. The latest development capture is 8/8 but not fully scored: the
  learner confirmed `faq-dev-004` as a content pass and `faq-dev-008` as a
  content fail; six cases remain unreviewed. The prior held-out split must not
  be reused for tuning.
- Continue to keep generated replies review-first and automation disabled.
  Do not run model/prompt tuning, a new promotion evaluation, or a latency
  profile under this UI milestone.

See the [Week 3 checklist](./WEEK-03-EXECUTION-CHECKLIST.md) and
[Week 4 checklist](./WEEK-04-EXECUTION-CHECKLIST.md) for the evidence and
full status.

## Implementation boundary

The learner approved the W5-00 design and delegated W5-01 shell implementation.
Keep draft/review integration for W5-02 through W5-04 separate; do not implement
or claim those milestones complete under this approval. If verified API or
build facts require a material design change, discuss it before proceeding.
