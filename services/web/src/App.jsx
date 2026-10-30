import { useState } from 'react'
import './App.css'

function QuestionForm({ question, onQuestionChange }) {
  return (
    <section className="panel" aria-labelledby="question-heading">
      <h2 id="question-heading">1. Support question</h2>
      <p id="question-help" className="helper">
        Use synthetic questions only. Do not enter real customer data.
      </p>
      <form onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="question">Customer question</label>
        <textarea
          id="question"
          name="question"
          rows={6}
          minLength={5}
          maxLength={3000}
          required
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          aria-describedby="question-help question-count generation-help"
        />
        <p id="question-count" className="helper character-count">
          {question.length} / 3000 characters
        </p>
        <button type="submit" disabled aria-describedby="generation-help">
          Generate draft
        </button>
        <p id="generation-help" className="helper">
          Draft requests will be connected in W5-02. This shell does not submit
          questions.
        </p>
      </form>
    </section>
  )
}

function DraftPanel() {
  return (
    <section className="panel" aria-labelledby="draft-heading">
      <h2 id="draft-heading">2. Draft</h2>
      <p className="empty-state">No draft has been requested.</p>
      <dl className="metadata">
        <div><dt>Trace ID</dt><dd>Not available</dd></div>
        <div><dt>Draft mode</dt><dd>Not available</dd></div>
        <div><dt>Review status</dt><dd>Not available</dd></div>
        <div><dt>Answer confidence</dt><dd>Unknown</dd></div>
      </dl>
    </section>
  )
}

function EvidencePanel() {
  return (
    <section className="panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">3. Evidence and checks</h2>
      <p className="empty-state">No evidence or checks have been loaded.</p>
      <p className="helper">
        Source excerpts, provenance, and returned checks will appear here.
        A citation or passing deterministic check is not proof of correctness.
      </p>
    </section>
  )
}

function ReviewPanel() {
  return (
    <section className="panel" aria-labelledby="review-heading">
      <h2 id="review-heading">4. Human review</h2>
      <label htmlFor="final-draft">Final reply</label>
      <textarea
        id="final-draft"
        rows={5}
        disabled
        aria-describedby="review-help"
        placeholder="A returned draft will be available for review here."
      />
      <div className="review-actions">
        <button type="button" disabled>Approve draft</button>
        <button type="button" disabled>Save edit</button>
        <button type="button" disabled>Reject</button>
      </div>
      <p id="review-help" className="helper">
        Review actions will be connected in W5-04. No review decision is saved
        and no message is sent by this shell.
      </p>
    </section>
  )
}

export default function App() {
  const [question, setQuestion] = useState('')

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
        <section className="notice" role="status" aria-labelledby="shell-heading">
          <h2 id="shell-heading">W5-01: shell only</h2>
          <p>
            Try the question field to explore React state. API actions are not
            connected yet. There is no model inference, review submission, or
            delivery from this page.
          </p>
        </section>
        <div className="workbench-grid">
          <QuestionForm question={question} onQuestionChange={setQuestion} />
          <DraftPanel />
          <EvidencePanel />
          <ReviewPanel />
        </div>
      </main>
      <footer>
        Backend review rules remain authoritative. This is a local learning
        workbench, not an authenticated production service.
      </footer>
    </div>
  )
}
