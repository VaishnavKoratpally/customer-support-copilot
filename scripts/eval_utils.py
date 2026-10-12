import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DatasetError(ValueError):
    pass


class EvaluationAPIError(RuntimeError):
    pass


def load_cases(path: Path, required_fields: set[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    case = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                if not isinstance(case, dict):
                    raise DatasetError(f"{path}:{line_number}: each JSONL row must be an object")
                missing = required_fields - case.keys()
                if missing:
                    raise DatasetError(
                        f"{path}:{line_number}: missing required fields: {', '.join(sorted(missing))}"
                    )
                case_id = case["id"]
                if not isinstance(case_id, str) or not case_id.strip():
                    raise DatasetError(f"{path}:{line_number}: id must be a non-empty string")
                if case_id in seen_ids:
                    raise DatasetError(f"{path}:{line_number}: duplicate id {case_id!r}")
                seen_ids.add(case_id)
                if not isinstance(case["question"], str) or not case["question"].strip():
                    raise DatasetError(f"{path}:{line_number}: question must be a non-empty string")
                cases.append(case)
    except OSError as exc:
        raise DatasetError(f"Could not read dataset {path}: {exc}") from exc

    if not cases:
        raise DatasetError(f"Dataset contains no cases: {path}")
    return cases


def call_support_draft(
    *,
    api_base_url: str,
    question: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/v1/support/draft"
    request = Request(
        url,
        data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise EvaluationAPIError(
            f"Support draft API returned HTTP {exc.code} {exc.reason}"
            + (f": {detail}" if detail else "")
        ) from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        reason = getattr(exc, "reason", exc)
        raise EvaluationAPIError(f"Could not call support draft API at {url}: {reason}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationAPIError("Support draft API returned invalid JSON") from exc

    if not isinstance(body, dict):
        raise EvaluationAPIError("Support draft API response must be a JSON object")
    if body.get("draft_mode") != "generated":
        raise EvaluationAPIError(
            "Support draft quality evaluation requires generated mode; "
            f"received draft_mode={body.get('draft_mode')!r}"
        )
    if not isinstance(body.get("draft"), str):
        raise EvaluationAPIError("Support draft API response is missing string field 'draft'")
    if not isinstance(body.get("citation_source_ids"), list) or not all(
        isinstance(source_id, str) for source_id in body["citation_source_ids"]
    ):
        raise EvaluationAPIError(
            "Support draft API response is missing string-list field 'citation_source_ids'"
        )
    if not isinstance(body.get("citation_contract_passed"), bool):
        raise EvaluationAPIError(
            "Support draft API response is missing boolean field 'citation_contract_passed'"
        )
    return body


def save_artifact(
    *,
    repo_root: Path,
    evaluation_name: str,
    api_base_url: str,
    dataset: Path,
    results: list[dict[str, Any]],
    run_error: str | None,
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if output_path is None:
        output_path = repo_root / "docs" / "evals" / "results" / f"{evaluation_name}-{timestamp}.json"
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    passed = sum(result.get("passed") is True for result in results)
    artifact = {
        "evaluation": evaluation_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "api_base_url": api_base_url.rstrip("/"),
        "dataset": str(dataset),
        "summary": {
            "total_cases": len(results),
            "passed_cases": passed,
            "failed_cases": len(results) - passed,
            "pass_rate": round(passed / len(results), 4) if results else 0.0,
            "run_error": run_error,
        },
        "results": results,
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Could not write evaluation artifact {output_path}: {exc}", file=sys.stderr)
        raise
    return output_path


def print_summary(
    *,
    evaluation_name: str,
    results: list[dict[str, Any]],
    artifact_path: Path,
    run_error: str | None,
) -> None:
    print(f"\n{evaluation_name} results")
    print("case_id | pass | score")
    print("-" * 30)
    for result in results:
        score = result.get("score")
        score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "n/a"
        print(f"{result['id']:<7} | {'yes' if result.get('passed') else 'no':<4} | {score_text}")

    passed = sum(result.get("passed") is True for result in results)
    total = len(results)
    print(f"\nPassed {passed}/{total} cases")
    if run_error:
        print(f"Run error: {run_error}")
    print(f"Artifact: {artifact_path}")
