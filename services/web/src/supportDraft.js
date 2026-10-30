function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function validateDraftResponse(value) {
  if (!isRecord(value)) {
    throw new Error('The API returned an invalid draft response: expected an object.')
  }

  for (const field of ['trace_id', 'draft']) {
    if (typeof value[field] !== 'string' || !value[field].trim()) {
      throw new Error(`The API returned an invalid draft response: missing or invalid ${field}.`)
    }
  }

  for (const field of ['draft_mode', 'review_status']) {
    if (value[field] != null && (typeof value[field] !== 'string' || !value[field].trim())) {
      throw new Error(`The API returned an invalid draft response: invalid ${field}.`)
    }
  }

  if (value.requires_human_review != null && typeof value.requires_human_review !== 'boolean') {
    throw new Error('The API returned an invalid draft response: invalid requires_human_review.')
  }
  if (value.answer_confidence != null && !Number.isFinite(value.answer_confidence)) {
    throw new Error('The API returned an invalid draft response: invalid answer_confidence.')
  }
  if (value.generation_metadata != null) {
    if (!isRecord(value.generation_metadata)) {
      throw new Error('The API returned an invalid draft response: invalid generation_metadata.')
    }
    const outcome = value.generation_metadata.outcome
    if (outcome != null && (typeof outcome !== 'string' || !outcome.trim())) {
      throw new Error('The API returned an invalid draft response: invalid generation outcome.')
    }
  }
  return value
}

function errorDetail(body) {
  if (typeof body?.detail === 'string' && body.detail.trim()) {
    return body.detail
  }
  if (Array.isArray(body?.detail)) {
    const messages = body.detail
      .filter((item) => isRecord(item) && typeof item.msg === 'string' && item.msg.trim())
      .map((item) => item.msg)
    if (messages.length) {
      return messages.join('; ')
    }
  }
  return 'The API did not provide a readable error detail.'
}

export async function requestSupportDraft(question, fetchRequest = fetch) {
  if (typeof question !== 'string' || question.trim().length < 5 || question.trim().length > 3000) {
    throw new Error('Enter a question containing 5 to 3,000 characters, excluding surrounding whitespace.')
  }

  let response
  try {
    response = await fetchRequest('/v1/support/draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question.trim() }),
    })
  } catch (cause) {
    throw new Error(
      'The draft request could not be confirmed: the API could not be reached or the connection was interrupted.',
      { cause },
    )
  }

  let body
  try {
    body = await response.json()
  } catch (cause) {
    throw new Error(
      `The API returned HTTP ${response.status}, but its response could not be read as JSON.`,
      { cause },
    )
  }

  if (!response.ok) {
    throw new Error(`Draft request failed (HTTP ${response.status}): ${errorDetail(body)}`)
  }
  return validateDraftResponse(body)
}
