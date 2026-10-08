import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                case = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(case, dict):
                raise ValueError(f"Expected a JSON object on line {line_number}.")
            cases.append(case)
    if not cases:
        raise ValueError(f"No evaluation cases found in {path}.")
    return cases


def call_retrieval(api_base_url: str, question: str, top_k: int) -> dict:
    url = f"{api_base_url.rstrip('/')}/v1/retrieval/query"
    payload = {"question": question, "top_k": top_k}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def evaluate_case(case: dict, response: dict) -> dict:
    expected = case.get("expected_retrieval_source_ids")
    if not isinstance(expected, list) or any(not isinstance(source_id, str) for source_id in expected):
        raise ValueError(
            f"Case {case.get('id', '<unknown>')} must define "
            "expected_retrieval_source_ids as a string array."
        )

    hits = response.get("hits")
    if not isinstance(hits, list):
        raise ValueError(f"Case {case.get('id', '<unknown>')} response has no hits array.")

    expected_source_ids = set(expected)
    actual_source_ids: set[str] = set()
    distances: list[float] = []
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("source_id"), str):
            raise ValueError(f"Case {case.get('id', '<unknown>')} has a malformed retrieval hit.")
        distance = hit.get("cosine_distance")
        if (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not math.isfinite(distance)
        ):
            raise ValueError(
                f"Case {case.get('id', '<unknown>')} hit has an invalid cosine_distance."
            )
        actual_source_ids.add(hit["source_id"])
        distances.append(float(distance))

    matched_source_ids = sorted(expected_source_ids & actual_source_ids)
    missing_source_ids = sorted(expected_source_ids - actual_source_ids)
    non_expected_source_ids = sorted(actual_source_ids - expected_source_ids)
    recall_at_k = (
        len(matched_source_ids) / len(expected_source_ids)
        if expected_source_ids
        else None
    )
    source_precision_at_k = (
        len(matched_source_ids) / len(actual_source_ids)
        if expected_source_ids and actual_source_ids
        else (0.0 if expected_source_ids else None)
    )

    return {
        "id": case.get("id", "<unknown>"),
        "expected_source_ids": sorted(expected_source_ids),
        "actual_source_ids": sorted(actual_source_ids),
        "missing_source_ids": missing_source_ids,
        "non_expected_source_ids": non_expected_source_ids,
        "recall_at_k": round(recall_at_k, 2) if recall_at_k is not None else None,
        "source_precision_at_k": (
            round(source_precision_at_k, 2)
            if source_precision_at_k is not None
            else None
        ),
        "nearest_cosine_distance": round(min(distances), 6) if distances else None,
    }


def print_results(results: list[dict]) -> None:
    print("\nWeek 3 Vector Retrieval Diagnostic\n")
    print("id                                   | Recall@k | Source P@k | other sources       | nearest distance")
    print("-" * 112)
    for result in results:
        recall = (
            f"{result['recall_at_k']:.2f}"
            if result["recall_at_k"] is not None
            else "n/a"
        )
        precision = (
            f"{result['source_precision_at_k']:.2f}"
            if result["source_precision_at_k"] is not None
            else "n/a"
        )
        distance = (
            f"{result['nearest_cosine_distance']:.4f}"
            if result["nearest_cosine_distance"] is not None
            else "n/a"
        )
        print(
            f"{result['id']:<36} | "
            f"{recall:<8} | "
            f"{precision:<10} | "
            f"{','.join(result['non_expected_source_ids']) or '-':<20} | "
            f"{distance}"
        )

    scored_results = [result for result in results if result["recall_at_k"] is not None]
    average_recall = (
        round(
            sum(result["recall_at_k"] for result in scored_results)
            / len(scored_results),
            2,
        )
        if scored_results
        else None
    )
    average_source_precision = (
        round(
            sum(result["source_precision_at_k"] for result in scored_results)
            / len(scored_results),
            2,
        )
        if scored_results
        else None
    )
    unscored_count = len(results) - len(scored_results)
    print("\nSummary")
    print(f"- Total cases: {len(results)}")
    print(f"- Cases with expected sources: {len(scored_results)}")
    print(f"- Average source Recall@k: {average_recall if average_recall is not None else 'n/a'}")
    print(
        "- Average unique-source precision@k: "
        f"{average_source_precision if average_source_precision is not None else 'n/a'}"
    )
    print(f"- Cases without expected sources (distance only): {unscored_count}")
    print("- Precision/recall use unique source IDs, not individual chunk hits.")
    print("- No evidence cutoff is applied; nearest distances and other sources are diagnostic only.")


def parse_args() -> argparse.Namespace:
    default_dataset = Path(__file__).resolve().parents[1] / "docs" / "evals" / "rag-week3-v1.jsonl"
    parser = argparse.ArgumentParser(
        description="Measure labeled source Recall@k and report raw cosine distances."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset,
        help="Path to a Week 3 retrieval JSONL dataset.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8000",
        help="Base URL for the API service.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.dataset.exists():
        print(f"Dataset file not found: {args.dataset}", file=sys.stderr)
        return 2

    try:
        cases = load_cases(args.dataset)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    results: list[dict] = []
    try:
        for case in cases:
            response = call_retrieval(
                api_base_url=args.api_base_url,
                question=case["question"],
                top_k=int(case["top_k"]),
            )
            results.append(evaluate_case(case, response))
    except urllib.error.HTTPError as exc:
        print(f"HTTP error from API: {exc.code} {exc.reason}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {args.api_base_url}: {exc.reason}", file=sys.stderr)
        return 3
    except (KeyError, TypeError, ValueError) as exc:
        print(f"Invalid evaluation data or API response: {exc}", file=sys.stderr)
        return 2

    print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
