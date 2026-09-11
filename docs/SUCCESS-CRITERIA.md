# v1 Success Criteria (Week 1 - Day 1)

This file defines how we judge whether the support copilot is working from a product and system perspective.

## 1) Latency targets

- **P50 response latency (default path): <= 4s**
- **P95 response latency (default path): <= 8s**
- **P95 response latency (escalated model path): <= 15s**

Why this matters:
- Low median latency keeps conversations fluid.
- P95 ensures reliability under real traffic variance, not just best-case demos.

## 2) Quality targets

- **Retrieval Recall@5: >= 0.75**
- **Groundedness pass rate: >= 0.90**
- **Citation correctness: >= 0.95**

Why this matters:
- Good retrieval is a prerequisite for good generation in RAG.
- Groundedness and citation correctness directly reduce hallucinated support claims.

## 3) Safety targets

- **High-risk intent mandatory review compliance: 100%**
- **Low-confidence mandatory review compliance: 100%**
- **Hallucination rate on eval suite: <= 0.08**

Why this matters:
- HITL is not optional for high-risk support actions.
- Policy gate failures are unacceptable even if answer quality appears high.

## 4) Cost and efficiency targets (free-first)

- **Default provider path:** local OSS (Ollama)
- **Escalation path usage:** <= 20% of total requests in steady state
- **Average tokens/request:** tracked and trended weekly

Why this matters:
- Free-first architecture stays viable only if escalations are controlled.
- Token and model usage trends expose routing inefficiencies early.

## 5) Operational reliability targets

- **API availability in local staging: >= 99% during active testing windows**
- **Error rate (5xx + timeout): <= 2%**
- **Critical trace completeness:** 100% for support-draft requests

Critical trace includes:
- request id / trace id
- intent/risk routing outcome
- retrieval confidence
- answer confidence
- HITL decision and reason

## 6) Promotion gates (v1)

No change is promoted to the next phase unless:

1. Safety metrics do not regress
2. Quality metrics are stable or improved
3. Latency remains within SLO thresholds
4. The related ADR has been updated with measured tradeoffs

