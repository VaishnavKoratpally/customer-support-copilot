import { useRef, useState } from 'react'
import { requestSupportDraft } from './supportDraft.js'
import './App.css'

function QuestionForm({ question, onQuestionChange, onSubmit, isSubmitting }) {
  return (
    <section className="panel" aria-labelledby="question-heading">
      <h2 id="question-heading">1. Support question</h2>
      <p id="question-help" className="helper">
        Use synthetic questions only. Do not enter real customer data.
      </p>
      <form onSubmit={onSubmit} aria-busy={isSubmitting}>
        <label htmlFor="question">Customer question</label>
        <textarea
          id="question"
          name="question"
          rows={6}
          minLength={5}
          maxLength={3000}
          required
          disabled={isSubmitting}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          aria-describedby="question-help question-count generation-help"
        />
        <p id="question-count" className="helper character-count">
          {question.length} / 3000 characters
        </p>
        <button type="submit" disabled={isSubmitting} aria-describedby="generation-help">
          {isSubmitting ? 'Requesting draft...' : 'Request draft'}
        </button>
        <p id="generation-help" className="helper">
          The backend determines whether this returns a preview or a generated
          reply. Starting a new request replaces the displayed result.
        </p>
      </form>
    </section>
  )
}

const requestMessages = {
  initial: 'No draft has been requested.',
  submitting: 'Requesting a draft. Local inference may take some time.',
  ready: 'Draft response received. Check its content mode and review status below.',
  error: 'No usable draft response was confirmed.',
}

const nonAnswerOutcomes = {
  no_retrieved_evidence: 'No evidence was retrieved.',
  clarification_needed: 'The backend requested clarification.',
  insufficient_evidence: 'The retrieved evidence was insufficient.',
  no_relevant_evidence: 'No relevant evidence was found.',
  conflicting_evidence: 'The retrieved evidence was conflicting.',
}

function DraftPanel({ request, headingRef }) {
  const draft = request.result
  const outcome = draft?.generation_metadata?.outcome
  let contentNotice = 'Content outcome unknown. Do not assume a customer reply was generated.'
  if (draft?.draft_mode === 'preview_only') {
    contentNotice = 'Preview only: no customer response was generated.'
  } else if (draft?.draft_mode === 'generated' && outcome === 'generated') {
    contentNotice = 'Generated reply received. Receiving a reply is not approval or proof of correctness.'
  } else if (Object.hasOwn(nonAnswerOutcomes, outcome)) {
    contentNotice = `${nonAnswerOutcomes[outcome]} No customer reply was generated.`
  }

  return (
    <section className="panel" aria-labelledby="draft-heading">
      <h2 id="draft-heading" ref={headingRef} tabIndex={-1}>2. Draft</h2>
      <p role="status">{requestMessages[request.status]}</p>
      {request.error && (
        <div className="error-state" role="alert">
          <p>{request.error}</p>
          <p>
            Your question is preserved. No automatic retry was made. A lost or
            unreadable response does not prove that nothing was saved.
            Submitting again may create another draft.
          </p>
        </div>
      )}
      {draft && (
        <>
          <h3>Submitted question</h3>
          <p className="draft-text">{request.submittedQuestion}</p>
          <p className="content-notice">{contentNotice}</p>
          <h3>Returned content</h3>
          <div className="draft-text">{draft.draft}</div>
        </>
      )}
      <dl className="metadata">
        <div><dt>Trace ID</dt><dd>{draft?.trace_id ?? 'Not available'}</dd></div>
        <div><dt>Draft mode</dt><dd>{draft?.draft_mode ?? 'Unknown'}</dd></div>
        <div><dt>Backend outcome</dt><dd>{outcome ?? 'Unknown'}</dd></div>
        <div><dt>Review status</dt><dd>{draft?.review_status ?? 'Unknown'}</dd></div>
        <div>
          <dt>Human review required</dt>
          <dd>
            {draft?.requires_human_review === true ? 'Yes'
              : draft?.requires_human_review === false ? 'No (reported by API)' : 'Unknown'}
          </dd>
        </div>
        <div><dt>Answer confidence</dt><dd>{draft?.answer_confidence ?? 'Unknown'}</dd></div>
      </dl>
    </section>
  )
}

function EvidencePanel() {
  return (
    <section className="panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">3. Evidence and checks</h2>
      <p className="empty-state">Evidence and check details will be displayed in W5-03.</p>
      <p className="helper">
        Source excerpts, provenance, and returned checks will appear here.
        A citation or passing deterministic check is not proof of correctness.
      </p>
    </section>
  )
}

function ReviewPanel({ traceId }) {
  return (
    <section className="panel" aria-labelledby="review-heading">
      <h2 id="review-heading">4. Human review</h2>
      <p className="helper">Active draft trace: {traceId ?? 'Not available'}</p>
      <label htmlFor="final-draft">Final reply</label>
      <textarea
        id="final-draft"
        rows={5}
        disabled
        aria-describedby="review-help"
        placeholder="Draft editing will be connected in W5-04."
      />
      <div className="review-actions">
        <button type="button" disabled>Approve draft</button>
        <button type="button" disabled>Save edit</button>
        <button type="button" disabled>Reject</button>
      </div>
      <p id="review-help" className="helper">
        Review actions will be connected in W5-04. No review decision is saved
        and no message is sent by this workbench.
      </p>
    </section>
  )
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [draftRequest, setDraftRequest] = useState({
    status: 'initial',
    submittedQuestion: '',
    result: null,
    error: null,
  })
  const requestInFlight = useRef(false)
  const draftHeadingRef = useRef(null)

  async function handleSubmit(event) {
    event.preventDefault()
    // The ref also blocks duplicate events before React renders the disabled button.
    if (requestInFlight.current) return

    const submittedQuestion = question.trim()
    requestInFlight.current = true
    setDraftRequest({ status: 'submitting', submittedQuestion, result: null, error: null })
    try {
      const result = await requestSupportDraft(submittedQuestion)
      setDraftRequest({ status: 'ready', submittedQuestion, result, error: null })
    } catch (error) {
      setDraftRequest({
        status: 'error',
        submittedQuestion,
        result: null,
        error: error instanceof Error ? error.message : 'An unexpected draft-request failure occurred.',
      })
    } finally {
      requestInFlight.current = false
      draftHeadingRef.current?.focus()
    }
  }

  return (
    <div className="page">
      <a className="skip-link" href="#workbench">Skip to workbench</a>
      <header className="page-header">
        <div>
          <p className="eyebrow">Customer Support Copilot</p>
          <h1>Reviewer workbench</h1>
        </div>
        <span className="badge">Local synthetic workspace</span>
      </header>
      <main id="workbench" tabIndex={-1}>
        <section className="notice" aria-labelledby="workbench-notice-heading">
          <h2 id="workbench-notice-heading">W5-02: question-to-draft flow</h2>
          <p>
            Draft requests are connected. Backend settings determine preview or
            generated replies. Evidence details and review actions are not
            connected yet. This page does not approve or send replies.
          </p>
        </section>
        <div className="workbench-grid">
          <QuestionForm
            question={question}
            onQuestionChange={setQuestion}
            onSubmit={handleSubmit}
            isSubmitting={draftRequest.status === 'submitting'}
          />
          <DraftPanel request={draftRequest} headingRef={draftHeadingRef} />
          <EvidencePanel />
          <ReviewPanel traceId={draftRequest.result?.trace_id} />
        </div>
      </main>
      <footer>
        Backend review rules remain authoritative. This is a local learning
        workbench, not an authenticated production service.
      </footer>
    </div>
  )
}
