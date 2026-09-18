# Rejection Reason Taxonomy (Day 5)

## Purpose

Define a controlled set of rejection reason codes for human review decisions so outcomes are:

- consistent across reviewers,
- analyzable for quality trends,
- actionable for prompt/retrieval/model improvements.

## Scope

Used in `POST /v1/support/review` when review status is `reject`.

If `status=reject`, `rejection_reason_code` is mandatory and must be one of the allowed codes below.

## Allowed reason codes

| Code | When to use | Typical follow-up |
|---|---|---|
| `policy-risk` | Draft may violate policy, legal, billing, security, or compliance rules. | Escalate to policy/security/legal queue; require manual response. |
| `missing-citations` | Draft lacks required evidence references or citations are incomplete. | Re-run retrieval; regenerate with evidence constraints. |
| `incorrect-facts` | Draft contains factual mistakes or contradictions with known sources. | Correct facts; improve retrieval grounding; add eval case. |
| `tone-issue` | Draft tone is inappropriate (too harsh, unclear, or not support-safe). | Human rewrite; tune style instructions in prompt. |
| `needs-human-judgment` | Case requires business discretion or irreversible decision not suitable for automation. | Keep human-owned path; optionally add policy rubric. |
| `insufficient-context` | Not enough ticket/customer/context info to answer safely. | Request missing details from customer; enrich context inputs. |

## Decision guidance

Use the **primary** root-cause reason code (the most direct reason for rejection), not every possible contributing issue.

Examples:
- If draft is factually wrong because citations are missing, prefer `missing-citations` as primary.
- If draft is accurate but action requires manager discretion, use `needs-human-judgment`.

## Why taxonomy instead of free text

1. Enables reliable analytics (rejection reason trends over time).
2. Supports targeted fixes (retrieval vs prompting vs policy gates).
3. Improves reviewer consistency across shifts/teams.

## Operational notes

- Rejection comments can still exist, but code must be from this taxonomy.
- New reason codes require explicit review and taxonomy update.
- Dashboard metrics should track rejection counts by code weekly.

## v1 review quality loop

For each rejected case:
1. Capture `rejection_reason_code`.
2. Capture question + draft + citations snapshot.
3. Assign remediation owner:
   - Retrieval issues -> retriever/chunking owner
   - Prompt/style issues -> prompting owner
   - Policy/risk issues -> HITL policy owner
4. Add regression test case when applicable.