# Confidence Scoring v0 (legacy generated-draft scaffold)

This heuristic is not used by the current preview-only draft runtime. Preview
responses return `NULL` for both confidence fields. Raw pgvector cosine
distance is not a confidence score, and this formula must not be used to
authorize generated answers until its inputs are calibrated and evaluated.

## Objective
Define a deterministic confidence score for support drafts that is easy to audit and tune.

## Formula (v0)

answer_confidence = round((retrieval_confidence * 0.7) + risk_bias, 2)

Where:
- risk_bias = 0.2 for low-risk intents
- risk_bias = 0.1 for medium/high-risk intents

## Rationale
- Retrieval quality is the strongest current signal, so it gets the largest weight.
- Low-risk intents receive a small positive bias to reduce unnecessary reviews.
- High/medium risk remain conservative by default.

## Known limitations
- Uses heuristic weights, not learned calibration.
- Does not yet use model uncertainty signals or human feedback loops.
- Assumes retrieval confidence quality is stable.

## Evolution path
- Add calibration using eval outcomes.
- Add route-specific weighting.
- Add penalties for missing or weak citations.