import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_utils import DatasetError, EvaluationAPIError, call_support_draft, load_cases


REQUIRED_CASE_FIELDS = {
    "case_id",
    "contract_id",
    "category",
    "families",
    "question",
    "expected_handling_after_promotion",
    "requires_human_review_after_promotion",
    "required_fact_ids",
    "permitted_fact_ids",
    "required_conditions",
    "unsupported_requests",
    "forbidden_claims",
    "safe_response_requirements",
}
STRING_LIST_FIELDS = {
    "families",
    "required_fact_ids",
    "permitted_fact_ids",
    "required_conditions",
    "unsupported_requests",
    "forbidden_claims",
    "safe_response_requirements",
}
REQUIRED_RESPONSE_FIELDS = {
    "trace_id",
    "intent",
    "risk_level",
    "model_used",
    "draft",
    "citations",
    "retrieval_confidence",
    "answer_confidence",
    "requires_human_review",
    "review_status",
    "escalation_reason",
    "citation_source_ids",
    "citation_contract_passed",
    "review_triggers",
    "draft_mode",
    "evidence_assessment",
    "generation_metadata",
}
REQUIRED_GENERATION_FIELDS = {
    "outcome",
    "generation_completion_verified",
    "automation_enabled",
    "final_response_checks",
    "automation_eligibility",
}


def load_pilot_cases(
    repo_root: Path,
    split: str,
) -> tuple[str, Path, list[dict[str, Any]], str]:
    contract_path = repo_root / "docs" / "evals" / "faq-pilot-contract-v1.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Could not read FAQ pilot contract {contract_path}: {exc}") from exc

    if contract.get("status") != "approved_frozen":
        raise DatasetError("FAQ pilot contract is not marked approved_frozen.")
    contract_id = contract.get("contract_id")
    case_sets = contract.get("case_sets")
    if not isinstance(contract_id, str) or not isinstance(case_sets, dict):
        raise DatasetError("FAQ pilot contract is missing its ID or case-set manifest.")
    split_config = case_sets.get(split)
    if not isinstance(split_config, dict):
        raise DatasetError(f"FAQ pilot contract has no {split!r} case set.")

    filename = split_config.get("filename")
    expected_count = split_config.get("case_count")
    expected_hash = split_config.get("canonical_sha256")
    if (
        not isinstance(filename, str)
        or not isinstance(expected_count, int)
        or not isinstance(expected_hash, str)
    ):
        raise DatasetError(f"FAQ pilot contract has an invalid {split!r} manifest.")

    dataset = repo_root / "docs" / "evals" / filename
    cases = load_cases(
        dataset,
        REQUIRED_CASE_FIELDS,
        id_field="case_id",
    )
    for case in cases:
        if case["contract_id"] != contract_id:
            raise DatasetError(
                f"{case['case_id']}: case contract_id does not match {contract_id!r}"
            )
        for field in STRING_LIST_FIELDS:
            values = case[field]
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise DatasetError(
                    f"{case['case_id']}: {field} must be a list of non-empty strings"
                )
        if not isinstance(case["category"], str):
            raise DatasetError(f"{case['case_id']}: category must be a string")
        if not isinstance(case["requires_human_review_after_promotion"], bool):
            raise DatasetError(
                f"{case['case_id']}: requires_human_review_after_promotion must be boolean"
            )

    canonical_json = json.dumps(
        cases,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    actual_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if len(cases) != expected_count or actual_hash != expected_hash:
        raise DatasetError(
            f"{split} cases do not match the frozen contract "
            f"(count {len(cases)}/{expected_count}, hash {actual_hash})."
        )
    return contract_id, dataset, cases, actual_hash


def validate_response(response: dict[str, Any]) -> None:
    missing = REQUIRED_RESPONSE_FIELDS - response.keys()
    if missing:
        raise EvaluationAPIError(
            f"Generated response is missing fields: {', '.join(sorted(missing))}"
        )
    if response["draft_mode"] != "generated":
        raise EvaluationAPIError(
            f"Expected generated mode; received {response['draft_mode']!r}"
        )
    generation = response["generation_metadata"]
    if not isinstance(generation, dict):
        raise EvaluationAPIError("Generated response is missing generation metadata.")
    missing_generation = REQUIRED_GENERATION_FIELDS - generation.keys()
    if missing_generation:
        raise EvaluationAPIError(
            "Generation metadata is missing fields: "
            + ", ".join(sorted(missing_generation))
        )
    if not isinstance(response["review_triggers"], list):
        raise EvaluationAPIError("Generated response review_triggers must be a list.")


def capture_case(
    case: dict[str, Any],
    *,
    api_base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = None
    error = None
    try:
        response = call_support_draft(
            api_base_url=api_base_url,
            question=case["question"],
            timeout_seconds=timeout_seconds,
        )
        validate_response(response)
    except EvaluationAPIError as exc:
        error = str(exc)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "case_id": case["case_id"],
        "case": case,
        "capture_status": "captured" if error is None else "error",
        "client_latency_ms": elapsed_ms,
        "http_status_code": 200 if error is None else None,
        "response": response if error is None else None,
        "error": error,
    }


def capture_cases(
    cases: list[dict[str, Any]],
    *,
    api_base_url: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    return [
        capture_case(
            case,
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
        )
        for case in cases
    ]


def save_capture_artifact(
    *,
    repo_root: Path,
    split: str,
    contract_id: str,
    dataset: Path,
    case_set_hash: str,
    api_base_url: str,
    timeout_seconds: float,
    results: list[dict[str, Any]],
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"faq-pilot-{split}-capture-{timestamp:%Y%m%dT%H%M%SZ}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    captured = sum(result["capture_status"] == "captured" for result in results)
    artifact = {
        "evaluation": "faq-pilot-capture",
        "split": split,
        "contract_id": contract_id,
        "case_set_canonical_sha256": case_set_hash,
        "dataset": dataset.relative_to(repo_root).as_posix(),
        "timestamp_utc": timestamp.isoformat(),
        "api_base_url": api_base_url.rstrip("/"),
        "timeout_seconds": timeout_seconds,
        "scoring_status": "not_performed",
        "summary": {
            "total_cases": len(results),
            "captured_cases": captured,
            "failed_cases": len(results) - captured,
        },
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture FAQ pilot API responses without scoring them."
    )
    parser.add_argument(
        "--split",
        choices=("development", "heldout"),
        default="development",
        help="Frozen case split to capture. Use heldout only for the final untouched run.",
    )
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        contract_id, dataset, cases, case_set_hash = load_pilot_cases(
            repo_root,
            args.split,
        )
    except DatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.timeout_seconds <= 0:
        print("--timeout-seconds must be greater than zero.", file=sys.stderr)
        return 2

    results = capture_cases(
        cases,
        api_base_url=args.api_base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        artifact_path = save_capture_artifact(
            repo_root=repo_root,
            split=args.split,
            contract_id=contract_id,
            dataset=dataset,
            case_set_hash=case_set_hash,
            api_base_url=args.api_base_url,
            timeout_seconds=args.timeout_seconds,
            results=results,
            output_path=args.output,
        )
    except OSError as exc:
        print(f"Could not save FAQ pilot capture artifact: {exc}", file=sys.stderr)
        return 2

    captured = sum(result["capture_status"] == "captured" for result in results)
    print(
        f"Captured {captured}/{len(results)} {args.split} cases; "
        f"scoring not performed. Artifact: {artifact_path}"
    )
    return 0 if captured == len(results) else 3


if __name__ == "__main__":
    raise SystemExit(main())
