import argparse
import json
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
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
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
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def evaluate_case(case: dict, response: dict) -> dict:
    expected_source_ids = set(case["expected_source_ids"])
    actual_source_ids = {hit["source_id"] for hit in response.get("hits", [])}
    matched_source_ids = sorted(expected_source_ids & actual_source_ids)
    missing_source_ids = sorted(expected_source_ids - actual_source_ids)

    confidence = float(response.get("retrieval_confidence", 0.0))
    min_confidence = float(case["min_confidence"])
    confidence_pass = confidence >= min_confidence
    sources_pass = len(missing_source_ids) == 0
    recall = len(matched_source_ids) / max(len(expected_source_ids), 1)
    passed = confidence_pass and sources_pass

    return {
        "id": case["id"],
        "passed": passed,
        "confidence": confidence,
        "min_confidence": min_confidence,
        "confidence_pass": confidence_pass,
        "expected_source_ids": sorted(expected_source_ids),
        "actual_source_ids": sorted(actual_source_ids),
        "missing_source_ids": missing_source_ids,
        "recall": round(recall, 2),
    }


def print_results(results: list[dict]) -> None:
    print("\nRetrieval Smoke Eval Results\n")
    print("id      | pass | conf | min | recall | missing_sources")
    print("-" * 72)
    for result in results:
        print(
            f"{result['id']:<7} | "
            f"{'yes' if result['passed'] else 'no ':<4} | "
            f"{result['confidence']:<4.2f} | "
            f"{result['min_confidence']:<3.2f} | "
            f"{result['recall']:<6.2f} | "
            f"{','.join(result['missing_source_ids']) if result['missing_source_ids'] else '-'}"
        )

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_recall = round(sum(r["recall"] for r in results) / max(total, 1), 2)
    print("\nSummary")
    print(f"- Total cases: {total}")
    print(f"- Passed: {passed}")
    print(f"- Failed: {total - passed}")
    print(f"- Pass rate: {round((passed / max(total, 1)) * 100, 2)}%")
    print(f"- Average recall: {avg_recall}")


def parse_args() -> argparse.Namespace:
    default_dataset = Path(__file__).resolve().parents[1] / "docs" / "evals" / "retrieval-smoke-v1.jsonl"
    parser = argparse.ArgumentParser(description="Run retrieval smoke evaluation against the API endpoint.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset,
        help="Path to JSONL dataset file.",
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

    print_results(results)
    all_passed = all(r["passed"] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

