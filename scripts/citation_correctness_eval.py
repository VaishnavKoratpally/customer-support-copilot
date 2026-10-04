import argparse
import sys
from pathlib import Path
from typing import Any

from eval_utils import (
    DatasetError,
    EvaluationAPIError,
    call_support_draft,
    load_cases,
    print_summary,
    save_artifact,
)


REQUIRED_FIELDS = {
    "id",
    "question",
    "expected_source_ids",
    "allow_extra_citations",
}


def validate_case(case: dict[str, Any]) -> None:
    expected_source_ids = case["expected_source_ids"]
    if not isinstance(expected_source_ids, list) or not all(
        isinstance(source_id, str) and source_id.strip()
        for source_id in expected_source_ids
    ):
        raise DatasetError(
            f"{case['id']}: expected_source_ids must be a list of non-empty strings"
        )
    if not expected_source_ids:
        raise DatasetError(f"{case['id']}: expected_source_ids must not be empty")
    if not isinstance(case["allow_extra_citations"], bool):
        raise DatasetError(f"{case['id']}: allow_extra_citations must be a boolean")


def evaluate_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected_source_ids = set(case["expected_source_ids"])
    actual_source_ids = set(response["citation_source_ids"])
    matched_source_ids = expected_source_ids & actual_source_ids
    missing_source_ids = sorted(expected_source_ids - actual_source_ids)
    unexpected_source_ids = sorted(actual_source_ids - expected_source_ids)

    precision = len(matched_source_ids) / len(actual_source_ids) if actual_source_ids else 0.0
    recall = len(matched_source_ids) / len(expected_source_ids)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    exact_match = actual_source_ids == expected_source_ids
    expected_sources_present = not missing_source_ids
    extras_allowed = case["allow_extra_citations"] or not unexpected_source_ids
    citation_contract_passed = response["citation_contract_passed"]
    passed = (
        expected_sources_present
        and extras_allowed
        and citation_contract_passed
    )

    return {
        "id": case["id"],
        "trace_id": response.get("trace_id"),
        "model_used": response.get("model_used"),
        "passed": passed,
        "score": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact_match": exact_match,
        "allow_extra_citations": case["allow_extra_citations"],
        "expected_source_ids": sorted(expected_source_ids),
        "actual_source_ids": sorted(actual_source_ids),
        "missing_source_ids": missing_source_ids,
        "unexpected_source_ids": unexpected_source_ids,
        "citation_contract_passed": citation_contract_passed,
    }


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run citation precision, recall, and exactness checks on support drafts."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=repo_root / "docs" / "evals" / "citation-correctness-v1.jsonl",
        help="Path to the citation correctness JSONL dataset.",
    )
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=600,
        help="Maximum wait for each support draft API call.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Artifact path (default: docs/evals/results/citation-correctness-<UTC timestamp>.json).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dataset = args.dataset if args.dataset.is_absolute() else repo_root / args.dataset

    try:
        cases = load_cases(dataset, REQUIRED_FIELDS)
        for case in cases:
            validate_case(case)
    except DatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    run_error = None
    for case in cases:
        try:
            response = call_support_draft(
                api_base_url=args.api_base_url,
                question=case["question"],
                timeout_seconds=args.timeout_seconds,
            )
        except EvaluationAPIError as exc:
            run_error = str(exc)
            results.append({"id": case["id"], "passed": False, "score": None, "error": run_error})
            break
        results.append(evaluate_case(case, response))

    try:
        artifact_path = save_artifact(
            repo_root=repo_root,
            evaluation_name="citation-correctness",
            api_base_url=args.api_base_url,
            dataset=dataset,
            results=results,
            run_error=run_error,
            output_path=args.output,
        )
    except OSError:
        return 2
    print_summary(
        evaluation_name="Citation correctness v1",
        results=results,
        artifact_path=artifact_path,
        run_error=run_error,
    )
    if run_error:
        return 3
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())