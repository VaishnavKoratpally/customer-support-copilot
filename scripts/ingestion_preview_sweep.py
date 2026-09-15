import json
import statistics
import urllib.request

API_URL = "http://localhost:8000/v1/ingestion/preview"

LONG_REFUNDS_TEXT = " ".join(
    [
        "Duplicate charges are reversed after review within two business days, "
        "and support requires invoice id, charge date, account email, and payment method confirmation."
    ]
    * 80
)

SAMPLE_CONTENT = f"""# Refunds
{LONG_REFUNDS_TEXT}

# Cancellations
Cancellations become effective at the end of the active billing term.
Prorated credits are only applicable for annual plans under specific conditions.

# Payment Failures
If a card payment fails, retry attempts happen automatically over 7 days.
Customers can update payment methods from account billing settings.

# Account Security
Unauthorized access reports require immediate support escalation and identity checks.
Password reset and MFA troubleshooting follow security policy workflows.
"""

TARGETS = [250, 450, 700]
OVERLAPS = [0, 50, 100]


def call_preview(target_chunk_tokens: int, overlap_tokens: int) -> dict:
    payload = {
        "metadata": {
            "source_key": "exp-01-policy-doc",
            "title": "Experiment Policy Document",
            "doc_type": "policy",
            "product_area": "billing",
            "policy_version": "exp-1",
            "effective_date": "2026-01-01",
            "access_scope": "internal",
        },
        "content": SAMPLE_CONTENT,
        "target_chunk_tokens": target_chunk_tokens,
        "overlap_tokens": overlap_tokens,
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    results = []

    for target in TARGETS:
        for overlap in OVERLAPS:
            response = call_preview(target, overlap)
            token_estimates = [c["token_estimate"] for c in response["chunks"]]
            avg_tokens = statistics.mean(token_estimates) if token_estimates else 0.0

            results.append(
                {
                    "target_chunk_tokens": target,
                    "overlap_tokens": overlap,
                    "total_chunks": response["total_chunks"],
                    "total_estimated_tokens": response["total_estimated_tokens"],
                    "avg_chunk_tokens_estimate": round(avg_tokens, 2),
                }
            )

    print("\nChunking Sweep Results\n")
    print("target | overlap | chunks | total_tokens | avg_chunk_tokens")
    print("-" * 62)
    for row in results:
        print(
            f"{row['target_chunk_tokens']:>6} | "
            f"{row['overlap_tokens']:>7} | "
            f"{row['total_chunks']:>6} | "
            f"{row['total_estimated_tokens']:>12} | "
            f"{row['avg_chunk_tokens_estimate']:>16}"
        )


if __name__ == "__main__":
    main()