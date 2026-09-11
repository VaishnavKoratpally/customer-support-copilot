# Domain Scope v1: B2B SaaS Billing + Account Support

## Target support outcomes

Focus the first release on high-frequency, high-clarity support intents where grounded answers and HITL controls provide immediate value.

## Supported intents (top 25)

| # | Intent | Risk Tier | Auto-send Allowed? |
|---|--------|-----------|--------------------|
| 1 | Duplicate charge reported | High | No |
| 2 | Refund eligibility question | High | No |
| 3 | Invoice copy request | Low | Yes (if confidence gate passes) |
| 4 | Payment failed troubleshooting | Medium | Yes (if confidence gate passes) |
| 5 | Card update instructions | Medium | Yes (if confidence gate passes) |
| 6 | Tax/VAT invoice query | Medium | Yes (if confidence gate passes) |
| 7 | Plan upgrade request | Medium | Yes (if confidence gate passes) |
| 8 | Plan downgrade request | Medium | Yes (if confidence gate passes) |
| 9 | Subscription cancellation request | High | No |
| 10 | Proration explanation | Medium | Yes (if confidence gate passes) |
| 11 | Trial extension request | Medium | Yes (if confidence gate passes) |
| 12 | Seat count increase request | Medium | Yes (if confidence gate passes) |
| 13 | Seat count decrease request | Medium | Yes (if confidence gate passes) |
| 14 | Account locked out | High | No |
| 15 | Password reset issue | Medium | Yes (if confidence gate passes) |
| 16 | Multi-factor auth trouble | High | No |
| 17 | Unauthorized login alert | High | No |
| 18 | User role/permission update | High | No |
| 19 | Add/remove teammate request | High | No |
| 20 | SSO setup guidance | Medium | Yes (if confidence gate passes) |
| 21 | Data export request | High | No |
| 22 | Account ownership transfer | High | No |
| 23 | Deletion/retention policy query | High | No |
| 24 | Billing contact change request | High | No |
| 25 | General product/billing FAQ | Low | Yes (if confidence gate passes) |

## Unsupported intents for v1

These are explicitly out of scope until later phases:

- legal contract interpretation
- custom pricing negotiations
- live outage RCA commitments
- compliance attestation authoring
- irreversible account actions without verified human review

## HITL policy guardrails

Human approval is mandatory when:

- risk tier is high
- answer confidence < configured threshold
- retrieval confidence < configured threshold
- citations are missing or not policy-aligned

## Why this scope

- Covers common support volume drivers in B2B SaaS.
- Includes both low-risk and high-risk intents, which is essential for learning HITL policy design.
- Enables concrete evaluation metrics on retrieval quality and escalation accuracy.

