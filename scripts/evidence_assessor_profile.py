import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.evidence_assessor import EvidenceAssessorError, OllamaEvidenceAssessor
from app.llm_provider import (
    OllamaGenerationResult,
    OllamaLLMProvider,
    OllamaProviderError,
)
from app.retrieval_repository import RetrievedChunk
from eval_utils import DatasetError, load_cases
from evidence_assessor_pilot import (
    PILOT_CASE_IDS,
    REQUIRED_FIELDS,
    RetrievalAPIError,
    parse_retrieved_chunks,
    validate_case,
)

DEFAULT_CASE_ID = "bi-005-credit-posting-date-partial-evidence"
PROCESS_QUERY_TIMEOUT_SECONDS = 10


class ProfileError(RuntimeError):
    pass


class CapturingStructuredGenerator:
    def __init__(self, provider: OllamaLLMProvider) -> None:
        self._provider = provider
        self.call_count = 0
        self.result: OllamaGenerationResult | None = None

    def generate_structured(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        if self.call_count != 0:
            raise ProfileError("A single-call profile may issue only one generation request.")
        self.call_count += 1
        self.result = self._provider.generate_structured_with_metrics(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )
        return self.result.text


def parse_cached_chunks(raw_chunks: Any, *, case_id: str) -> tuple[RetrievedChunk, ...]:
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise ProfileError(f"{case_id}: cached retrieval must contain at least one chunk.")

    hits: list[dict[str, Any]] = []
    for index, chunk in enumerate(raw_chunks):
        if not isinstance(chunk, dict):
            raise ProfileError(f"{case_id}: cached chunk {index} must be an object.")
        text = chunk.get("text")
        if not isinstance(text, str):
            raise ProfileError(f"{case_id}: cached chunk {index} has no text field.")
        hits.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "source_id": chunk.get("source_id"),
                "title": chunk.get("title"),
                "policy_version": chunk.get("policy_version"),
                "effective_date": chunk.get("effective_date"),
                "access_scope": chunk.get("access_scope"),
                "chunk_index": chunk.get("chunk_index"),
                "section_path": chunk.get("section_path"),
                "excerpt": text,
                "cosine_distance": chunk.get("cosine_distance"),
            }
        )

    try:
        return parse_retrieved_chunks(hits, case_id=case_id)
    except RetrievalAPIError as exc:
        raise ProfileError(f"{case_id}: cached retrieval chunks are invalid: {exc}") from exc


def load_cached_retrieval(
    *,
    artifact_path: Path,
    case_id: str,
    question: str,
) -> tuple[tuple[RetrievedChunk, ...], float | None]:
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"Could not read retrieval artifact {artifact_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Retrieval artifact {artifact_path} is invalid JSON.") from exc

    if not isinstance(artifact, dict) or not isinstance(artifact.get("results"), list):
        raise ProfileError("Retrieval artifact must contain a results array.")
    source_dataset = artifact.get("dataset")
    if (
        not isinstance(source_dataset, str)
        or Path(source_dataset).name != "rag-week3-v1.jsonl"
    ):
        raise ProfileError(
            "The retrieval artifact must come from the development dataset "
            "rag-week3-v1.jsonl."
        )
    matching_results = [
        result
        for result in artifact["results"]
        if isinstance(result, dict) and result.get("id") == case_id
    ]
    if len(matching_results) != 1:
        raise ProfileError(
            f"Retrieval artifact must contain exactly one result for {case_id}."
        )

    result = matching_results[0]
    if result.get("question") != question:
        raise ProfileError(
            f"Retrieval artifact question does not match development case {case_id}."
        )
    retrieval = result.get("retrieval")
    if not isinstance(retrieval, dict) or retrieval.get("mode") == "fixture":
        raise ProfileError(
            f"{case_id}: profiling requires cached API-retrieved chunks, not a fixture."
        )

    chunks = parse_cached_chunks(retrieval.get("chunks"), case_id=case_id)
    latency = result.get("latency")
    retrieval_seconds = (
        latency.get("retrieval_seconds") if isinstance(latency, dict) else None
    )
    if retrieval_seconds is not None and (
        isinstance(retrieval_seconds, bool)
        or not isinstance(retrieval_seconds, (int, float))
        or retrieval_seconds < 0
    ):
        raise ProfileError(f"{case_id}: cached retrieval latency is invalid.")
    return chunks, retrieval_seconds


def _optional_nonnegative_integer(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileError(f"Ollama /api/ps field {field_name!r} must be a non-negative integer.")
    return value


def get_ollama_processes(*, base_url: str) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/ps"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(
            request,
            timeout=PROCESS_QUERY_TIMEOUT_SECONDS,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ProfileError(
            f"Ollama /api/ps returned HTTP {exc.code} {exc.reason}"
            + (f": {detail}" if detail else "")
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        reason = getattr(exc, "reason", exc)
        raise ProfileError(f"Could not query Ollama process state at {url}: {reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError("Ollama /api/ps returned invalid JSON.") from exc

    if not isinstance(body, dict) or not isinstance(body.get("models"), list):
        raise ProfileError("Ollama /api/ps response must contain a models array.")

    processes: list[dict[str, Any]] = []
    for index, raw_process in enumerate(body["models"]):
        if not isinstance(raw_process, dict):
            raise ProfileError(f"Ollama /api/ps model {index} must be an object.")
        name = raw_process.get("name")
        if not isinstance(name, str):
            name = raw_process.get("model")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError(f"Ollama /api/ps model {index} has no model name.")
        processes.append(
            {
                "name": name,
                "size_bytes": _optional_nonnegative_integer(
                    raw_process.get("size"),
                    field_name="size",
                ),
                "size_vram_bytes": _optional_nonnegative_integer(
                    raw_process.get("size_vram"),
                    field_name="size_vram",
                ),
                "context_length": _optional_nonnegative_integer(
                    raw_process.get("context_length"),
                    field_name="context_length",
                ),
                "expires_at": raw_process.get("expires_at"),
            }
        )
    return processes


def summarize_model_residency(
    processes: list[dict[str, Any]],
    *,
    model_name: str,
) -> dict[str, Any]:
    matching = [process for process in processes if process["name"] == model_name]
    if len(matching) > 1:
        raise ProfileError(f"Ollama reported multiple active processes for {model_name}.")
    if not matching:
        return {
            "loaded": False,
            "size_bytes": None,
            "size_vram_bytes": None,
            "estimated_non_vram_bytes": None,
            "vram_to_model_size_ratio": None,
            "context_length": None,
            "expires_at": None,
        }

    process = matching[0]
    size_bytes = process["size_bytes"]
    size_vram_bytes = process["size_vram_bytes"]
    has_sizes = (
        isinstance(size_bytes, int)
        and not isinstance(size_bytes, bool)
        and size_bytes > 0
        and isinstance(size_vram_bytes, int)
        and not isinstance(size_vram_bytes, bool)
    )
    return {
        "loaded": True,
        "size_bytes": size_bytes,
        "size_vram_bytes": size_vram_bytes,
        "estimated_non_vram_bytes": (
            max(size_bytes - size_vram_bytes, 0) if has_sizes else None
        ),
        "vram_to_model_size_ratio": (
            round(size_vram_bytes / size_bytes, 4) if has_sizes else None
        ),
        "context_length": process["context_length"],
        "expires_at": process["expires_at"],
    }


def _seconds_from_nanoseconds(value: int | None) -> float | None:
    return round(value / 1_000_000_000, 6) if value is not None else None


def serialize_generation_metrics(
    result: OllamaGenerationResult | None,
    *,
    wall_seconds: float,
    call_count: int,
) -> dict[str, Any]:
    if result is None:
        return {
            "assessor_generation_calls": call_count,
            "wall_seconds": round(wall_seconds, 3),
            "prompt_tokens": None,
            "generated_tokens": None,
            "model_load_seconds": None,
            "prompt_evaluation_seconds": None,
            "generation_seconds": None,
            "ollama_total_seconds": None,
            "generated_tokens_per_second": None,
            "done_reason": None,
        }

    metrics = result.metrics
    eval_seconds = _seconds_from_nanoseconds(metrics.eval_duration_ns)
    return {
        "assessor_generation_calls": call_count,
        "wall_seconds": round(wall_seconds, 3),
        "prompt_tokens": metrics.prompt_eval_count,
        "generated_tokens": metrics.eval_count,
        "model_load_seconds": _seconds_from_nanoseconds(metrics.load_duration_ns),
        "prompt_evaluation_seconds": _seconds_from_nanoseconds(
            metrics.prompt_eval_duration_ns
        ),
        "generation_seconds": eval_seconds,
        "ollama_total_seconds": _seconds_from_nanoseconds(
            metrics.total_duration_ns
        ),
        "generated_tokens_per_second": (
            round(metrics.eval_count / eval_seconds, 3)
            if metrics.eval_count is not None and eval_seconds is not None and eval_seconds > 0
            else None
        ),
        "done_reason": metrics.done_reason,
    }


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Profile one evidence-assessor generation using cached development retrieval."
        )
    )
    parser.add_argument(
        "--case-id",
        choices=PILOT_CASE_IDS,
        default=DEFAULT_CASE_ID,
        help="Development case from rag-week3-v1.jsonl.",
    )
    parser.add_argument(
        "--retrieval-artifact",
        type=Path,
        required=True,
        help="Prior development evaluation artifact containing this case's API hits.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Profile artifact path; defaults to a timestamped results file.",
    )
    return parser.parse_args()


def run_profile(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    repo_root = Path(__file__).resolve().parents[1]
    dataset = repo_root / "docs" / "evals" / "rag-week3-v1.jsonl"
    retrieval_artifact = (
        args.retrieval_artifact
        if args.retrieval_artifact.is_absolute()
        else repo_root / args.retrieval_artifact
    )
    try:
        cases = load_cases(dataset, REQUIRED_FIELDS)
    except DatasetError as exc:
        raise ProfileError(f"Could not load the development dataset: {exc}") from exc
    case = next((case for case in cases if case["id"] == args.case_id), None)
    if case is None:
        raise ProfileError(f"Unknown development case ID: {args.case_id}")
    validate_case(case)

    chunks, cached_retrieval_seconds = load_cached_retrieval(
        artifact_path=retrieval_artifact,
        case_id=case["id"],
        question=case["question"],
    )
    settings = get_settings()
    processes_before = get_ollama_processes(base_url=settings.ollama_base_url)
    residency_before = summarize_model_residency(
        processes_before,
        model_name=settings.evidence_assessor_model,
    )

    provider = OllamaLLMProvider(
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    capturing_generator = CapturingStructuredGenerator(provider)
    assessor = OllamaEvidenceAssessor(
        generator=capturing_generator,
        model_name=settings.evidence_assessor_model,
    )
    assessment_started = time.perf_counter()
    assessment_error = None
    decision = None
    try:
        decision = assessor.assess(
            question=case["question"],
            retrieved_chunks=chunks,
        )
    except EvidenceAssessorError as exc:
        assessment_error = str(exc)
    assessment_wall_seconds = time.perf_counter() - assessment_started

    processes_after: list[dict[str, Any]] | None = None
    residency_after: dict[str, Any] | None = None
    process_after_error = None
    try:
        processes_after = get_ollama_processes(base_url=settings.ollama_base_url)
        residency_after = summarize_model_residency(
            processes_after,
            model_name=settings.evidence_assessor_model,
        )
    except ProfileError as exc:
        process_after_error = str(exc)

    timestamp = datetime.now(timezone.utc)
    output_path = args.output
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"evidence-assessor-profile-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    artifact = {
        "evaluation": "evidence-assessor-performance-profile",
        "timestamp_utc": timestamp.isoformat(),
        "case_id": case["id"],
        "dataset": str(dataset),
        "retrieval_input": {
            "source": str(retrieval_artifact),
            "mode": "cached_api_retrieval",
            "retrieval_seconds_from_source_run": (
                round(cached_retrieval_seconds, 3)
                if cached_retrieval_seconds is not None
                else None
            ),
            "chunk_count": len(chunks),
            "source_ids": list(dict.fromkeys(chunk.source_id for chunk in chunks)),
            "retrieval_was_reissued": False,
        },
        "assessor_model": settings.evidence_assessor_model,
        "model_residency": {
            "state_before_inference": (
                "warm" if residency_before["loaded"] else "cold"
            ),
            "before": residency_before,
            "after": residency_after,
            "after_query_error": process_after_error,
            "processes_before": processes_before,
            "processes_after": processes_after,
            "memory_note": (
                "Ollama /api/ps size and size_vram are byte counts. "
                "The non-VRAM estimate is size minus size_vram; confirm processor "
                "placement with `ollama ps`."
            ),
        },
        "generation": serialize_generation_metrics(
            capturing_generator.result,
            wall_seconds=assessment_wall_seconds,
            call_count=capturing_generator.call_count,
        ),
        "assessment": {
            "expected_status": case["evidence_sufficiency"],
            "actual_status": decision.status if decision is not None else None,
            "status_matches_expected": (
                decision.status == case["evidence_sufficiency"]
                if decision is not None
                else None
            ),
            "error": assessment_error,
        },
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ProfileError(f"Could not write profile artifact {output_path}: {exc}") from exc
    return artifact, output_path


def _display(value: Any) -> str:
    return "unavailable" if value is None else str(value)


def main() -> int:
    args = parse_args()
    try:
        artifact, output_path = run_profile(args)
    except (ProfileError, OllamaProviderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    generation = artifact["generation"]
    residency = artifact["model_residency"]
    after = residency["after"] or {}
    assessment = artifact["assessment"]
    print("Evidence assessor single-call profile")
    print(f"Case: {artifact['case_id']} (development set)")
    print(f"Model: {artifact['assessor_model']}")
    print(f"State before inference: {residency['state_before_inference']}")
    print(
        "Tokens: prompt={0}, generated={1}, generation rate={2} tokens/s".format(
            _display(generation["prompt_tokens"]),
            _display(generation["generated_tokens"]),
            _display(generation["generated_tokens_per_second"]),
        )
    )
    print(
        "Ollama timing seconds: load={0}, prompt_eval={1}, generation={2}, total={3}".format(
            _display(generation["model_load_seconds"]),
            _display(generation["prompt_evaluation_seconds"]),
            _display(generation["generation_seconds"]),
            _display(generation["ollama_total_seconds"]),
        )
    )
    print(f"Assessment wall time: {generation['wall_seconds']} seconds")
    print(
        "Model memory bytes after inference: size={0}, size_vram={1}, "
        "estimated_non_vram={2}".format(
            _display(after.get("size_bytes")),
            _display(after.get("size_vram_bytes")),
            _display(after.get("estimated_non_vram_bytes")),
        )
    )
    print(
        "Status: expected={0}, actual={1}".format(
            assessment["expected_status"],
            _display(assessment["actual_status"]),
        )
    )
    if assessment["error"]:
        print(f"Assessment error: {assessment['error']}")
    if residency["after_query_error"]:
        print(f"Post-inference residency query error: {residency['after_query_error']}")
    print(f"Profile artifact: {output_path}")
    return 1 if assessment["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
