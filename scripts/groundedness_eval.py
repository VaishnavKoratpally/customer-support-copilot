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
    "required_phrases",
    "forbidden_phrases",
    "expected_source_ids",
}


def validate_case(case: dict[str, Any]) -> None:
    for field in ("required_phrases", "forbidden_phrases", "expected_source_ids"):
        values = case[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise DatasetError(f"{case['id']}: {field} must be a list of non-empty strings")
    if not case["required_phrases"]:
        raise DatasetError(f"{case['id']}: required_phrases must not be empty")
    if not case["expected_source_ids"]:
        raise DatasetError(f"{case['id']}: expected_source_ids must not be empty")


def evaluate_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    draft = response["draft"]
    draft_lower = draft.casefold()

    required_checks = {
        phrase: phrase.casefold() in draft_lower for phrase in case["required_phrases"]
    }
    forbidden_checks = {
        phrase: phrase.casefold() not in draft_lower for phrase in case["forbidden_phrases"]
    }
    expected_source_ids = set(case["expected_source_ids"])
    actual_source_ids = set(response["citation_source_ids"])
    missing_source_ids = sorted(expected_source_ids - actual_source_ids)
    source_coverage_passed = not missing_source_ids
    citation_contract_passed = response["citation_contract_passed"]

    checks = list(required_checks.values()) + list(forbidden_checks.values()) + [
        source_coverage_passed,
        citation_contract_passed,
    ]
    passed_checks = sum(checks)
    score = passed_checks / len(checks)
    return {
        "id": case["id"],
        "trace_id": response.get("trace_id"),
        "model_used": response.get("model_used"),
        "passed": all(checks),
        "score": round(score, 4),
        "required_phrase_checks": required_checks,
        "forbidden_phrase_checks": forbidden_checks,
        "expected_source_ids": sorted(expected_source_ids),
        "actual_source_ids": sorted(actual_source_ids),
        "missing_source_ids": missing_source_ids,
        "source_coverage_passed": source_coverage_passed,
        "citation_contract_passed": citation_contract_passed,
        "draft": draft,
    }


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run deterministic phrase-and-source groundedness checks on support drafts."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=repo_root / "docs" / "evals" / "groundedness-v1.jsonl",
        help="Path to the groundedness JSONL dataset.",
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
        help="Artifact path (default: docs/evals/results/groundedness-<UTC timestamp>.json).",
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
            evaluation_name="groundedness",
            api_base_url=args.api_base_url,
            dataset=dataset,
            results=results,
            run_error=run_error,
            output_path=args.output,
        )
    except OSError:
        return 2
    print_summary(
        evaluation_name="Groundedness v1",
        results=results,
        artifact_path=artifact_path,
        run_error=run_error,
    )
    if run_error:
        return 3
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())