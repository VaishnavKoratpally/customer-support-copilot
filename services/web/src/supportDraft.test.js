import assert from 'node:assert/strict'
import test from 'node:test'
import { requestSupportDraft } from './supportDraft.js'

const question = 'How do I download an issued invoice?'
const result = {
  trace_id: 'test-trace',
  draft: 'An illustrative response for a frontend test.',
  draft_mode: 'generated',
  review_status: 'pending_review',
  requires_human_review: true,
  answer_confidence: null,
  generation_metadata: { outcome: 'generated' },
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

test('posts only the trimmed question to the relative draft endpoint once', async () => {
  const calls = []
  const draft = await requestSupportDraft(`  ${question}  `, async (...args) => {
    calls.push(args)
    return jsonResponse(result)
  })
  assert.deepEqual(calls, [[
    '/v1/support/draft',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    },
  ]])
  assert.deepEqual(draft, result)
})

test('preserves preview-only, absent optional fields, and extra evidence fields', async () => {
  const preview = {
    trace_id: 'preview-trace',
    draft: 'No customer response was generated.',
    draft_mode: 'preview_only',
    citations: [{ source_id: 'synthetic-source' }],
  }
  assert.deepEqual(
    await requestSupportDraft(question, async () => jsonResponse(preview)),
    preview,
  )
})

test('preserves abstention outcomes rather than manufacturing a generated answer', async () => {
  const abstention = {
    ...result,
    draft: 'No verified support guidance was retrieved.',
    generation_metadata: { outcome: 'no_retrieved_evidence' },
  }
  assert.deepEqual(
    await requestSupportDraft(question, async () => jsonResponse(abstention)),
    abstention,
  )
})

test('leaves absent and future status values for explicit unknown/raw display', async () => {
  const future = { trace_id: 'future-trace', draft: 'Content', review_status: 'future_status' }
  assert.deepEqual(
    await requestSupportDraft(question, async () => jsonResponse(future)),
    future,
  )
})

test('preserves explicit false and zero instead of treating them as missing', async () => {
  const values = { ...result, requires_human_review: false, answer_confidence: 0 }
  assert.deepEqual(
    await requestSupportDraft(question, async () => jsonResponse(values)),
    values,
  )
})

for (const invalid of ['', '    ', 'abcd', 'x'.repeat(3001), null]) {
  test(`rejects invalid question without a request (${String(invalid).length} characters)`, async () => {
    let calls = 0
    await assert.rejects(requestSupportDraft(invalid, async () => {
      calls += 1
      return jsonResponse(result)
    }), /5 to 3,000 characters/)
    assert.equal(calls, 0)
  })
}

for (const length of [5, 3000]) {
  test(`accepts the question length boundary ${length}`, async () => {
    await requestSupportDraft('x'.repeat(length), async () => jsonResponse(result))
  })
}

for (const status of [422, 502, 503]) {
  test(`reports HTTP ${status} and backend detail without retrying`, async () => {
    let calls = 0
    await assert.rejects(requestSupportDraft(question, async () => {
      calls += 1
      return jsonResponse({ detail: 'Synthetic backend failure.' }, status)
    }), new RegExp(`HTTP ${status}.*Synthetic backend failure`))
    assert.equal(calls, 1)
  })
}

test('reports FastAPI validation messages', async () => {
  await assert.rejects(requestSupportDraft(question, async () => jsonResponse({
    detail: [{ loc: ['body', 'question'], msg: 'String should have at least 5 characters' }],
  }, 422)), /HTTP 422.*at least 5 characters/)
})

test('reports status even when an error body has no usable detail', async () => {
  await assert.rejects(
    requestSupportDraft(question, async () => jsonResponse({ detail: {} }, 500)),
    /HTTP 500.*did not provide a readable error detail/,
  )
})

for (const status of [200, 502]) {
  test(`reports unreadable JSON for HTTP ${status}`, async () => {
    await assert.rejects(
      requestSupportDraft(question, async () => new Response('<html>Not JSON</html>', { status })),
      new RegExp(`HTTP ${status}.*could not be read as JSON`),
    )
  })
}

test('reports network failure as unconfirmed and does not retry', async () => {
  let calls = 0
  await assert.rejects(requestSupportDraft(question, async () => {
    calls += 1
    throw new TypeError('Failed to fetch')
  }), /could not be confirmed/)
  assert.equal(calls, 1)
})

for (const [label, invalid] of [
  ['non-object', []],
  ['missing trace', { draft: 'Content' }],
  ['blank draft', { ...result, draft: ' ' }],
  ['mode type', { ...result, draft_mode: true }],
  ['status type', { ...result, review_status: {} }],
  ['review flag type', { ...result, requires_human_review: 'false' }],
  ['confidence type', { ...result, answer_confidence: '0.9' }],
  ['metadata type', { ...result, generation_metadata: [] }],
  ['outcome type', { ...result, generation_metadata: { outcome: false } }],
]) {
  test(`rejects invalid displayed response fields: ${label}`, async () => {
    await assert.rejects(
      requestSupportDraft(question, async () => jsonResponse(invalid)),
      /invalid draft response/,
    )
  })
}
