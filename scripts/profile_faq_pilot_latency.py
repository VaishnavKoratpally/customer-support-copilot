import argparse
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capture_faq_pilot_eval import capture_case, load_pilot_cases
from evidence_assessor_profile import (
    ProfileError as OllamaProfileError,
    get_ollama_processes,
)
from eval_utils import DatasetError


COLD_CASE_ID = "faq-dev-003"
WARM_REQUESTS = 20
P50_TARGET_MS = 4000
P95_TARGET_MS = 8000


class LatencyProfileError(RuntimeError):
    pass


def select_cold_case(cases: list[dict[str, Any]]) -> dict[str, Any]:
    matching = [case for case in cases if case["case_id"] == COLD_CASE_ID]
    if len(matching) != 1:
        raise LatencyProfileError(
            f"The frozen development set must contain exactly one {COLD_CASE_ID} case."
        )
    return matching[0]


def schedule_warm_cases(
    cases: list[dict[str, Any]],
    *,
    request_count: int = WARM_REQUESTS,
) -> list[dict[str, Any]]:
    if not cases:
        raise LatencyProfileError("The frozen development set contains no cases.")
    if request_count < WARM_REQUESTS:
        raise LatencyProfileError(
            f"The warm profile requires at least {WARM_REQUESTS} requests."
        )
    return [cases[index % len(cases)] for index in range(request_count)]


def require_ollama_unloaded(processes: list[dict[str, Any]]) -> None:
    if processes:
        model_names = ", ".join(
            str(process.get("name", "<unknown>")) for process in processes
        )
        raise LatencyProfileError(
            "The cold sample requires Ollama to have no resident models; "
            f"currently loaded: {model_names}. Restart the Ollama service, then retry."
        )


def _optional_nonnegative_number(value: Any, *, field_name: str) -> int | float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise LatencyProfileError(
            f"Response metadata field {field_name!r} must be a finite non-negative number."
        )
    return value


def _model_metrics(value: Any, *, stage: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LatencyProfileError(f"{stage} model metrics must be an object or null.")

    metrics: dict[str, Any] = {}
    for source, target in (
        ("prompt_eval_count", "prompt_tokens"),
        ("eval_count", "generated_tokens"),
        ("load_duration_ns", "load_duration_ns"),
        ("prompt_eval_duration_ns", "prompt_eval_duration_ns"),
        ("eval_duration_ns", "generation_duration_ns"),
        ("total_duration_ns", "total_duration_ns"),
    ):
        metrics[target] = _optional_nonnegative_number(
            value.get(source),
            field_name=f"{stage}_metrics.{source}",
        )
    done_reason = value.get("done_reason")
    if done_reason is not None and not isinstance(done_reason, str):
        raise LatencyProfileError(f"{stage} model done_reason must be a string or null.")
    metrics["done_reason"] = done_reason
    return metrics


def extract_profile_metrics(response: dict[str, Any]) -> dict[str, Any]:
    metadata = response.get("generation_metadata")
    if not isinstance(metadata, dict):
        raise LatencyProfileError("Generated response is missing generation_metadata.")

    retrieval_seconds = _optional_nonnegative_number(
        metadata.get("retrieval_elapsed_seconds"),
        field_name="retrieval_elapsed_seconds",
    )
    if retrieval_seconds is None:
        raise LatencyProfileError(
            "API response has no retrieval timing; rebuild/restart the API with the "
            "W4-05 instrumentation before profiling."
        )

    return {
        "intent": response.get("intent"),
        "risk_level": response.get("risk_level"),
        "outcome": metadata.get("outcome"),
        "review_status": response.get("review_status"),
        "requires_human_review": response.get("requires_human_review"),
        "automation_enabled": metadata.get("automation_enabled"),
        "eligible_candidate": (
            metadata.get("automation_eligibility", {}).get("eligible_candidate")
            if isinstance(metadata.get("automation_eligibility"), dict)
            else None
        ),
        "retrieved_chunk_count": metadata.get("retrieved_chunk_count"),
        "retrieval_elapsed_seconds": retrieval_seconds,
        "assessor_elapsed_seconds": _optional_nonnegative_number(
            metadata.get("assessor_elapsed_seconds"),
            field_name="assessor_elapsed_seconds",
        ),
        "assessor_model": metadata.get("assessor_model"),
        "assessor_max_output_tokens": metadata.get("assessor_max_output_tokens"),
        "assessor_system_prompt_sha256": metadata.get(
            "assessor_system_prompt_sha256"
        ),
        "assessor_user_prompt_sha256": metadata.get("assessor_user_prompt_sha256"),
        "assessor_schema_sha256": metadata.get("assessor_schema_sha256"),
        "assessor_metrics": _model_metrics(
            metadata.get("assessor_metrics"),
            stage="assessor",
        ),
        "generator_elapsed_seconds": _optional_nonnegative_number(
            metadata.get("generator_elapsed_seconds"),
            field_name="generator_elapsed_seconds",
        ),
        "generator_model": metadata.get("generator_model"),
        "generator_max_output_tokens": metadata.get("generator_max_output_tokens"),
        "generator_system_prompt_sha256": metadata.get(
            "generator_system_prompt_sha256"
        ),
        "generator_user_prompt_sha256": metadata.get("generator_user_prompt_sha256"),
        "generator_schema_sha256": metadata.get("generator_schema_sha256"),
        "generator_metrics": _model_metrics(
            metadata.get("generator_metrics"),
            stage="generator",
        ),
    }


def review_first_violation(response: dict[str, Any]) -> str | None:
    metadata = response.get("generation_metadata")
    if not isinstance(metadata, dict):
        return "Generation metadata is missing; review-first mode cannot be verified."
    if metadata.get("automation_enabled") is not False:
        return "Automation must remain disabled during the latency profile."
    if (
        response.get("requires_human_review") is not True
        or response.get("review_status") != "pending_review"
    ):
        return "Every profile response must remain pending human review."
    return None


def capture_profile_sample(
    case: dict[str, Any],
    *,
    sample_type: str,
    sequence_number: int,
    api_base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    sample = capture_case(
        case,
        api_base_url=api_base_url,
        timeout_seconds=timeout_seconds,
    )
    sample["sample_type"] = sample_type
    sample["sequence_number"] = sequence_number
    sample["category"] = case["category"]
    sample["families"] = case["families"]

    response = sample.get("response")
    if isinstance(response, dict):
        validation_errors: list[str] = []
        try:
            sample["profile_metrics"] = extract_profile_metrics(response)
        except LatencyProfileError as exc:
            validation_errors.append(str(exc))
        violation = review_first_violation(response)
        if violation is not None:
            validation_errors.append(violation)
        if validation_errors:
            sample["profile_validation_errors"] = validation_errors
    return sample


def capture_error_requires_stop(sample: dict[str, Any]) -> str | None:
    if sample.get("capture_status") != "error":
        return None
    error = sample.get("error")
    if not isinstance(error, str):
        return "The API request failed without a diagnostic message."
    if error.startswith("Support draft API returned HTTP 5"):
        return None
    return f"Cannot continue profiling after a non-server API error: {error}"


def summarize_latencies(samples: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    for sample in samples:
        value = sample.get("client_latency_ms")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise LatencyProfileError(
                "Each attempted request must have a finite non-negative client latency."
            )
        values.append(float(value))

    if not values:
        p50_ms = None
        p95_ms = None
    elif len(values) == 1:
        p50_ms = values[0]
        p95_ms = values[0]
    else:
        p50_ms = statistics.median(values)
        p95_ms = statistics.quantiles(
            values,
            n=100,
            method="inclusive",
        )[94]

    return {
        "attempts": len(samples),
        "captured": sum(sample.get("capture_status") == "captured" for sample in samples),
        "errors": sum(sample.get("capture_status") != "captured" for sample in samples),
        "p50_client_latency_ms": round(p50_ms, 2) if p50_ms is not None else None,
        "p95_client_latency_ms": round(p95_ms, 2) if p95_ms is not None else None,
        "percentile_method": "median p50; linear interpolation p95 (inclusive)",
    }


def _load_duration_ns(sample: dict[str, Any]) -> list[int]:
    metrics = sample.get("profile_metrics")
    if not isinstance(metrics, dict):
        return []
    durations: list[int] = []
    for stage in ("assessor_metrics", "generator_metrics"):
        stage_metrics = metrics.get(stage)
        if not isinstance(stage_metrics, dict):
            continue
        value = stage_metrics.get("load_duration_ns")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            durations.append(value)
    return durations


def _count_field(samples: list[dict[str, Any]], field: str) -> dict[str, int]:
    values = [
        sample["profile_metrics"].get(field)
        for sample in samples
        if isinstance(sample.get("profile_metrics"), dict)
        and sample["profile_metrics"].get(field) is not None
    ]
    return {
        str(value): count
        for value, count in sorted(Counter(values).items(), key=lambda item: str(item[0]))
    }


def _unique_values(samples: list[dict[str, Any]], field: str) -> list[Any]:
    values = {
        sample["profile_metrics"].get(field)
        for sample in samples
        if isinstance(sample.get("profile_metrics"), dict)
        and sample["profile_metrics"].get(field) is not None
    }
    return sorted(values, key=str)


def _model_prompt_output_configuration(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    configuration_fields = (
        "assessor_model",
        "assessor_max_output_tokens",
        "assessor_system_prompt_sha256",
        "assessor_schema_sha256",
        "generator_model",
        "generator_max_output_tokens",
        "generator_system_prompt_sha256",
        "generator_schema_sha256",
    )
    return {
        field: _unique_values(samples, field)
        for field in configuration_fields
    } | {
        "per_request_prompt_hashes": [
            {
                "sample_type": sample["sample_type"],
                "case_id": sample["case_id"],
                "assessor_user_prompt_sha256": sample["profile_metrics"].get(
                    "assessor_user_prompt_sha256"
                ),
                "generator_user_prompt_sha256": sample["profile_metrics"].get(
                    "generator_user_prompt_sha256"
                ),
            }
            for sample in samples
            if isinstance(sample.get("profile_metrics"), dict)
        ],
        "ollama_options": {
            "temperature": 0,
            "stream": False,
            "think": False,
            "context_length": (
                "Not set per request; uses the Ollama model/service configuration."
            ),
        },
    }


def _target_comparison(summary: dict[str, Any]) -> dict[str, Any]:
    p50 = summary["p50_client_latency_ms"]
    p95 = summary["p95_client_latency_ms"]
    return {
        "p50_target_ms": P50_TARGET_MS,
        "p95_target_ms": P95_TARGET_MS,
        "p50_met": None if p50 is None else p50 <= P50_TARGET_MS,
        "p95_met": None if p95 is None else p95 <= P95_TARGET_MS,
    }


def summarize_profile(
    samples: list[dict[str, Any]],
    *,
    ollama_processes_before: list[dict[str, Any]],
) -> dict[str, Any]:
    cold_samples = [sample for sample in samples if sample["sample_type"] == "cold"]
    warm_samples = [sample for sample in samples if sample["sample_type"] == "warm"]
    cold = cold_samples[0] if cold_samples else None
    cold_load_observed = bool(cold and _load_duration_ns(cold))
    cold_verified = not ollama_processes_before and cold_load_observed
    warm_summary = summarize_latencies(warm_samples)
    combined_summary = summarize_latencies(samples)
    routing = {
        field: _count_field(samples, field)
        for field in (
            "intent",
            "risk_level",
            "outcome",
            "review_status",
            "automation_enabled",
            "eligible_candidate",
        )
    }

    return {
        "cold": {
            "attempts": len(cold_samples),
            "case_id": cold.get("case_id") if cold else None,
            "capture_status": cold.get("capture_status") if cold else None,
            "client_latency_ms": (
                cold.get("client_latency_ms") if cold else None
            ),
            "ollama_unloaded_before_first_request": not ollama_processes_before,
            "model_load_observed": cold_load_observed,
            "model_load_durations_ns": _load_duration_ns(cold) if cold else [],
            "cold_load_verified": cold_verified,
        },
        "warm": {
            **warm_summary,
            "requests_with_nonzero_model_load_duration": sum(
                bool(_load_duration_ns(sample)) for sample in warm_samples
            ),
            "targets": _target_comparison(warm_summary),
        },
        "combined": {
            **combined_summary,
            "targets": _target_comparison(combined_summary),
        },
        "routing_mix": routing,
        "model_prompt_output_configuration": _model_prompt_output_configuration(
            samples
        ),
        "quality": {
            "profile_semantic_scoring": "not_performed",
            "responses_with_captured_profile_metrics": sum(
                isinstance(sample.get("profile_metrics"), dict)
                for sample in samples
            ),
        },
    }


def save_profile_artifact(
    *,
    repo_root: Path,
    contract_id: str,
    dataset: Path,
    case_set_hash: str,
    api_base_url: str,
    ollama_base_url: str,
    timeout_seconds: float,
    hardware_state: str,
    power_state: str,
    ollama_processes_before: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    run_error: str | None,
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"faq-pilot-latency-profile-{timestamp:%Y%m%dT%H%M%SZ}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    artifact = {
        "evaluation": "faq-pilot-latency-profile",
        "profile_version": "w4-05-v1",
        "split": "development",
        "contract_id": contract_id,
        "case_set_canonical_sha256": case_set_hash,
        "dataset": dataset.relative_to(repo_root).as_posix(),
        "timestamp_utc": timestamp.isoformat(),
        "api_base_url": api_base_url.rstrip("/"),
        "ollama_base_url": ollama_base_url.rstrip("/"),
        "timeout_seconds": timeout_seconds,
        "hardware_state": hardware_state,
        "power_state": power_state,
        "execution": {
            "sequential": True,
            "cold_case_id": COLD_CASE_ID,
            "warm_requests_required": WARM_REQUESTS,
            "warm_case_order": [
                sample["case_id"]
                for sample in samples
                if sample["sample_type"] == "warm"
            ],
            "ollama_processes_before_first_request": ollama_processes_before,
        },
        "summary": summarize_profile(
            samples,
            ollama_processes_before=ollama_processes_before,
        ),
        "scoring_status": "not_performed",
        "run_error": run_error,
        "results": samples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile one cold and 20 sequential warm FAQ requests using only "
            "the frozen development cases."
        )
    )
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument(
        "--hardware-state",
        required=True,
        help="Observed GPU/model hardware and driver details for this run.",
    )
    parser.add_argument(
        "--power-state",
        required=True,
        help="Observed AC/battery, battery-saver, and active power-plan state.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _run_error(
    samples: list[dict[str, Any]],
    *,
    cold_verified: bool,
    validation_error: str | None,
) -> str | None:
    if validation_error is not None:
        return validation_error
    if len([sample for sample in samples if sample["sample_type"] == "warm"]) < WARM_REQUESTS:
        return f"The profile stopped before completing {WARM_REQUESTS} warm requests."
    if any(sample.get("capture_status") != "captured" for sample in samples):
        return "One or more API requests failed; latency includes their measured wall time."
    if not cold_verified:
        return "The first request's cold model load could not be verified."
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    if args.timeout_seconds <= 0:
        print("--timeout-seconds must be greater than zero.", file=sys.stderr)
        return 2
    if not args.hardware_state.strip() or not args.power_state.strip():
        print("--hardware-state and --power-state must not be blank.", file=sys.stderr)
        return 2

    try:
        contract_id, dataset, cases, case_set_hash = load_pilot_cases(
            repo_root,
            "development",
        )
        cold_case = select_cold_case(cases)
        warm_cases = schedule_warm_cases(cases)
        ollama_processes_before = get_ollama_processes(
            base_url=args.ollama_base_url,
        )
        require_ollama_unloaded(ollama_processes_before)
    except (DatasetError, LatencyProfileError, OllamaProfileError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    samples: list[dict[str, Any]] = []
    validation_error: str | None = None
    sample_plan = [("cold", 0, cold_case)] + [
        ("warm", index, case)
        for index, case in enumerate(warm_cases, start=1)
    ]
    for sample_type, sequence_number, case in sample_plan:
        sample = capture_profile_sample(
            case,
            sample_type=sample_type,
            sequence_number=sequence_number,
            api_base_url=args.api_base_url,
            timeout_seconds=args.timeout_seconds,
        )
        samples.append(sample)
        errors = sample.get("profile_validation_errors")
        if isinstance(errors, list) and errors:
            validation_error = "; ".join(errors)
            break
        stop_reason = capture_error_requires_stop(sample)
        if stop_reason is not None:
            validation_error = stop_reason
            break

    profile_summary = summarize_profile(
        samples,
        ollama_processes_before=ollama_processes_before,
    )
    run_error = _run_error(
        samples,
        cold_verified=profile_summary["cold"]["cold_load_verified"],
        validation_error=validation_error,
    )
    try:
        artifact_path = save_profile_artifact(
            repo_root=repo_root,
            contract_id=contract_id,
            dataset=dataset,
            case_set_hash=case_set_hash,
            api_base_url=args.api_base_url,
            ollama_base_url=args.ollama_base_url,
            timeout_seconds=args.timeout_seconds,
            hardware_state=args.hardware_state.strip(),
            power_state=args.power_state.strip(),
            ollama_processes_before=ollama_processes_before,
            samples=samples,
            run_error=run_error,
            output_path=args.output,
        )
    except OSError as exc:
        print(f"Could not save FAQ pilot latency artifact: {exc}", file=sys.stderr)
        return 2

    cold = profile_summary["cold"]
    warm = profile_summary["warm"]
    combined = profile_summary["combined"]
    print(
        f"Cold {cold['case_id']}: {cold['client_latency_ms']} ms; "
        f"model load verified={cold['cold_load_verified']}"
    )
    print(
        f"Warm: {warm['captured']}/{WARM_REQUESTS} captured; "
        f"p50={warm['p50_client_latency_ms']} ms; "
        f"p95={warm['p95_client_latency_ms']} ms"
    )
    print(
        f"Combined: {combined['captured']}/{combined['attempts']} captured; "
        f"p50={combined['p50_client_latency_ms']} ms; "
        f"p95={combined['p95_client_latency_ms']} ms"
    )
    target_results = [
        warm["targets"]["p50_met"],
        warm["targets"]["p95_met"],
        combined["targets"]["p50_met"],
        combined["targets"]["p95_met"],
    ]
    if any(result is False for result in target_results):
        print("A measured latency target was missed; promotion remains blocked.")
    elif run_error is not None:
        print("Latency targets were not established because the profile is incomplete.")
    elif all(result is True for result in target_results):
        print("Measured latency targets met; other promotion gates still apply.")
    else:
        print("Latency targets were not assessed because measurements are missing.")
    if run_error:
        print(f"Profile incomplete: {run_error}", file=sys.stderr)
    print(f"Artifact: {artifact_path}")
    return 0 if run_error is None else 3


if __name__ == "__main__":
    raise SystemExit(main())
