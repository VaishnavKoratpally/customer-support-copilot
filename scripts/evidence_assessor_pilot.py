import argparse
import json
import math
import socket
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.evidence_assessment import (
    EvidenceFinding,
    aggregate_evidence_sufficiency_status,
)
from app.evidence_assessor import EvidenceAssessorError, OllamaEvidenceAssessor
from app.llm_provider import OllamaLLMProvider
from app.retrieval_repository import RetrievedChunk
from eval_utils import DatasetError, load_cases

PILOT_CASE_IDS = (
    "bi-002-initial-review-window-supported",
    "ar-002-reset-link-expiry-unsupported",
    "ar-005-ambiguous-account-access",
    "bi-005-credit-posting-date-partial-evidence",
    "oc-001-invoice-download-not-in-corpus",
)

EVIDENCE_STATUSES = {
    "sufficient",
    "partial",
    "insufficient",
    "none",
    "clarification_needed",
    "conflicting",
}

REQUIRED_FIELDS = {
    "id",
    "question",
    "top_k",
    "expected_retrieval_source_ids",
    "evidence_sufficiency",
    "expected_action",
    "supporting_facts",
    "claims_to_avoid",
    "expected_human_review",
}

GOLD_REQUIRED_FIELDS = {"id", "question", "assessor_gold"}
ASSESSOR_FINDINGS = {
    "supported",
    "contradicted",
    "related_but_not_supported",
    "no_relevant_evidence",
    "conflicting",
}
DETERMINED_FINDINGS = {"supported", "contradicted"}


class RetrievalAPIError(RuntimeError):
    pass


def validate_case(case: dict[str, Any]) -> None:
    case_id = case["id"]
    top_k = case["top_k"]
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
        raise DatasetError(f"{case_id}: top_k must be an integer between 1 and 10.")

    if case["evidence_sufficiency"] not in EVIDENCE_STATUSES:
        raise DatasetError(
            f"{case_id}: unsupported evidence_sufficiency "
            f"{case['evidence_sufficiency']!r}."
        )

    for field in (
        "expected_retrieval_source_ids",
        "supporting_facts",
        "claims_to_avoid",
    ):
        values = case[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise DatasetError(f"{case_id}: {field} must be a list of non-empty strings.")

    if not isinstance(case["expected_action"], str) or not case["expected_action"].strip():
        raise DatasetError(f"{case_id}: expected_action must be a non-empty string.")
    if not isinstance(case["expected_human_review"], bool):
        raise DatasetError(f"{case_id}: expected_human_review must be a boolean.")


def validate_gold_evidence(
    evidence: Any,
    *,
    case_id: str,
    field_name: str,
) -> list[dict[str, str]]:
    if not isinstance(evidence, list):
        raise DatasetError(f"{case_id}: {field_name} must be a list.")

    validated: list[dict[str, str]] = []
    required_fields = {"source_id", "section_path", "quote"}
    for index, reference in enumerate(evidence):
        if not isinstance(reference, dict) or set(reference) != required_fields:
            raise DatasetError(
                f"{case_id}: {field_name}[{index}] must contain exactly "
                "source_id, section_path, and quote."
            )
        for field_name_in_reference in required_fields:
            value = reference[field_name_in_reference]
            if not isinstance(value, str) or not value.strip():
                raise DatasetError(
                    f"{case_id}: {field_name}[{index}].{field_name_in_reference} "
                    "must be a non-empty string."
                )
        validated.append(reference)
    return validated


def validate_assessor_gold(
    *,
    case_id: str,
    expected_status: str,
    expected_source_ids: set[str],
    assessor_gold: Any,
) -> None:
    required_fields = {
        "requested_information",
        "supporting_facts",
        "clarification_topics",
    }
    if not isinstance(assessor_gold, dict) or set(assessor_gold) != required_fields:
        raise DatasetError(
            f"{case_id}: assessor_gold must contain exactly "
            "requested_information, supporting_facts, and clarification_topics."
        )

    requested_information = assessor_gold["requested_information"]
    supporting_facts = assessor_gold["supporting_facts"]
    clarification_topics = assessor_gold["clarification_topics"]
    if not isinstance(requested_information, list):
        raise DatasetError(f"{case_id}: assessor_gold.requested_information must be a list.")
    if not isinstance(supporting_facts, list):
        raise DatasetError(f"{case_id}: assessor_gold.supporting_facts must be a list.")
    if not isinstance(clarification_topics, list) or not all(
        isinstance(topic, str) and topic.strip() for topic in clarification_topics
    ):
        raise DatasetError(
            f"{case_id}: assessor_gold.clarification_topics must be a list "
            "of non-empty strings."
        )

    requested_ids: set[str] = set()
    findings: set[EvidenceFinding] = set()
    for index, item in enumerate(requested_information):
        item_path = f"assessor_gold.requested_information[{index}]"
        item_fields = {
            "id",
            "requested_information",
            "finding",
            "answer",
            "evidence",
        }
        if not isinstance(item, dict) or set(item) != item_fields:
            raise DatasetError(
                f"{case_id}: {item_path} has an invalid shape."
            )
        for field_name in ("id", "requested_information"):
            value = item[field_name]
            if not isinstance(value, str) or not value.strip():
                raise DatasetError(
                    f"{case_id}: {item_path}.{field_name} must be a non-empty string."
                )
        if item["id"] in requested_ids:
            raise DatasetError(f"{case_id}: duplicate requested-information id {item['id']!r}.")
        requested_ids.add(item["id"])

        finding = item["finding"]
        if not isinstance(finding, str) or finding not in ASSESSOR_FINDINGS:
            raise DatasetError(f"{case_id}: {item_path} has unsupported finding {finding!r}.")
        findings.add(finding)

        evidence = validate_gold_evidence(
            item["evidence"],
            case_id=case_id,
            field_name=f"{item_path}.evidence",
        )
        for reference in evidence:
            if reference["source_id"] not in expected_source_ids:
                raise DatasetError(
                    f"{case_id}: {item_path} cites unexpected source "
                    f"{reference['source_id']!r}."
                )

        answer = item["answer"]
        if finding in DETERMINED_FINDINGS:
            if not isinstance(answer, str) or not answer.strip() or not evidence:
                raise DatasetError(
                    f"{case_id}: {item_path} needs a declarative answer and evidence."
                )
        elif finding in {"related_but_not_supported", "conflicting"}:
            if answer is not None or not evidence:
                raise DatasetError(
                    f"{case_id}: {item_path} needs null answer and evidence."
                )
            if finding == "conflicting" and len(
                {(ref["source_id"], ref["section_path"]) for ref in evidence}
            ) < 2:
                raise DatasetError(
                    f"{case_id}: conflicting gold needs evidence from at least "
                    "two distinct source sections."
                )
        elif answer is not None or evidence:
            raise DatasetError(
                f"{case_id}: no_relevant_evidence gold must have null answer "
                "and no evidence."
            )

    for index, fact in enumerate(supporting_facts):
        fact_path = f"assessor_gold.supporting_facts[{index}]"
        if not isinstance(fact, dict) or set(fact) != {"claim", "evidence"}:
            raise DatasetError(f"{case_id}: {fact_path} has an invalid shape.")
        if not isinstance(fact["claim"], str) or not fact["claim"].strip():
            raise DatasetError(f"{case_id}: {fact_path}.claim must be a non-empty string.")
        evidence = validate_gold_evidence(
            fact["evidence"],
            case_id=case_id,
            field_name=f"{fact_path}.evidence",
        )
        if not evidence:
            raise DatasetError(f"{case_id}: {fact_path} needs at least one evidence quote.")
        for reference in evidence:
            if reference["source_id"] not in expected_source_ids:
                raise DatasetError(
                    f"{case_id}: {fact_path} cites unexpected source "
                    f"{reference['source_id']!r}."
                )

    if clarification_topics:
        if expected_status != "clarification_needed":
            raise DatasetError(
                f"{case_id}: clarification topics conflict with expected status "
                f"{expected_status!r}."
            )
        if requested_information or supporting_facts:
            raise DatasetError(
                f"{case_id}: clarification gold cannot include findings or supporting facts."
            )
    else:
        if expected_status == "clarification_needed":
            raise DatasetError(f"{case_id}: clarification_needed gold requires clarification topics.")
        if not requested_information:
            raise DatasetError(
                f"{case_id}: non-clarification gold needs at least one requested-information item."
            )

    derived_status = aggregate_evidence_sufficiency_status(
        findings,
        has_supporting_facts=bool(supporting_facts),
        clarification_needed=bool(clarification_topics),
    )

    if derived_status != expected_status:
        raise DatasetError(
            f"{case_id}: assessor_gold derives {derived_status!r}, "
            f"but the evaluation dataset expects {expected_status!r}."
        )


def load_assessor_gold(
    path: Path,
    cases: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    gold_cases = load_cases(path, GOLD_REQUIRED_FIELDS)
    cases_by_id = {case["id"]: case for case in cases}
    gold_by_id = {case["id"]: case for case in gold_cases}
    missing_ids = sorted(cases_by_id.keys() - gold_by_id.keys())
    extra_ids = sorted(gold_by_id.keys() - cases_by_id.keys())
    if missing_ids or extra_ids:
        raise DatasetError(
            f"Assessor gold case IDs do not match the evaluation dataset; "
            f"missing={missing_ids}, extra={extra_ids}."
        )

    annotations: dict[str, dict[str, Any]] = {}
    for case_id, case in cases_by_id.items():
        gold_case = gold_by_id[case_id]
        if gold_case["question"] != case["question"]:
            raise DatasetError(
                f"{case_id}: assessor gold question does not match the evaluation dataset."
            )
        assessor_gold = gold_case["assessor_gold"]
        validate_assessor_gold(
            case_id=case_id,
            expected_status=case["evidence_sufficiency"],
            expected_source_ids=set(case["expected_retrieval_source_ids"]),
            assessor_gold=assessor_gold,
        )
        annotations[case_id] = assessor_gold
    return annotations


def select_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str] | None,
    all_cases: bool,
) -> list[dict[str, Any]]:
    if all_cases and case_ids:
        raise DatasetError("--all-cases cannot be combined with --case-id.")

    if all_cases:
        return cases

    selected_ids = case_ids or list(PILOT_CASE_IDS)
    if len(selected_ids) != len(set(selected_ids)):
        raise DatasetError("--case-id values must be unique.")

    cases_by_id = {case["id"]: case for case in cases}
    unknown_ids = [case_id for case_id in selected_ids if case_id not in cases_by_id]
    if unknown_ids:
        raise DatasetError(f"Unknown evaluation case IDs: {', '.join(unknown_ids)}")
    return [cases_by_id[case_id] for case_id in selected_ids]


def call_retrieval(
    *,
    api_base_url: str,
    question: str,
    top_k: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/v1/retrieval/query"
    request = urllib.request.Request(
        url,
        data=json.dumps({"question": question, "top_k": top_k}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RetrievalAPIError(
            f"Retrieval API returned HTTP {exc.code} {exc.reason}"
            + (f": {detail}" if detail else "")
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        reason = getattr(exc, "reason", exc)
        raise RetrievalAPIError(
            f"Could not call retrieval API at {url}: {reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RetrievalAPIError("Retrieval API returned invalid JSON.") from exc

    if not isinstance(body, dict) or not isinstance(body.get("hits"), list):
        raise RetrievalAPIError(
            "Retrieval API response must be an object containing a hits array."
        )
    return body


def parse_retrieved_chunks(
    hits: list[Any],
    *,
    case_id: str,
) -> tuple[RetrievedChunk, ...]:
    chunks: list[RetrievedChunk] = []
    required_string_fields = (
        "chunk_id",
        "source_id",
        "title",
        "policy_version",
        "effective_date",
        "access_scope",
        "section_path",
        "excerpt",
    )
    for index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            raise RetrievalAPIError(
                f"{case_id}: retrieval hit {index} must be a JSON object."
            )
        for field in required_string_fields:
            if not isinstance(hit.get(field), str):
                raise RetrievalAPIError(
                    f"{case_id}: retrieval hit {index} is missing string field {field!r}."
                )
        chunk_index = hit.get("chunk_index")
        cosine_distance = hit.get("cosine_distance")
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
            raise RetrievalAPIError(
                f"{case_id}: retrieval hit {index} has an invalid chunk_index."
            )
        if (
            isinstance(cosine_distance, bool)
            or not isinstance(cosine_distance, (int, float))
            or not math.isfinite(cosine_distance)
        ):
            raise RetrievalAPIError(
                f"{case_id}: retrieval hit {index} has an invalid cosine_distance."
            )
        try:
            chunk_id = UUID(hit["chunk_id"])
            effective_date = date.fromisoformat(hit["effective_date"])
        except ValueError as exc:
            raise RetrievalAPIError(
                f"{case_id}: retrieval hit {index} has an invalid UUID or effective_date."
            ) from exc

        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                source_id=hit["source_id"],
                title=hit["title"],
                policy_version=hit["policy_version"],
                effective_date=effective_date,
                access_scope=hit["access_scope"],
                chunk_index=chunk_index,
                section_path=hit["section_path"],
                text=hit["excerpt"],
                cosine_distance=float(cosine_distance),
            )
        )
    return tuple(chunks)


def serialize_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "source_id": chunk.source_id,
        "title": chunk.title,
        "policy_version": chunk.policy_version,
        "effective_date": chunk.effective_date.isoformat(),
        "access_scope": chunk.access_scope,
        "chunk_index": chunk.chunk_index,
        "section_path": chunk.section_path,
        "text": chunk.text,
        "cosine_distance": chunk.cosine_distance,
    }


def build_expected_result(
    case: dict[str, Any],
    assessor_gold: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evidence_sufficiency": case["evidence_sufficiency"],
        "expected_action": case["expected_action"],
        "expected_retrieval_source_ids": case["expected_retrieval_source_ids"],
        "required_answer_facts": case["supporting_facts"],
        "claims_to_avoid": case["claims_to_avoid"],
        "human_review_required": case["expected_human_review"],
        "assessor_gold": assessor_gold,
    }


def source_retrieval_metrics(
    *,
    expected_source_ids: list[str],
    chunks: tuple[RetrievedChunk, ...],
) -> dict[str, Any]:
    expected = set(expected_source_ids)
    actual = {chunk.source_id for chunk in chunks}
    matched = sorted(expected & actual)
    return {
        "expected_source_ids": sorted(expected),
        "actual_source_ids": sorted(actual),
        "missing_source_ids": sorted(expected - actual),
        "other_retrieved_source_ids": sorted(actual - expected),
        "source_recall_at_k": (
            round(len(matched) / len(expected), 4) if expected else None
        ),
    }


def gold_evidence_retrieval_metrics(
    *,
    assessor_gold: dict[str, Any],
    chunks: tuple[RetrievedChunk, ...],
) -> dict[str, Any]:
    evidence_references = [
        reference
        for item in assessor_gold["requested_information"]
        for reference in item["evidence"]
    ]
    evidence_references.extend(
        reference
        for fact in assessor_gold["supporting_facts"]
        for reference in fact["evidence"]
    )

    missing_references = [
        reference
        for reference in evidence_references
        if not any(
            chunk.source_id == reference["source_id"]
            and chunk.section_path == reference["section_path"]
            and reference["quote"] in chunk.text
            for chunk in chunks
        )
    ]
    return {
        "expected_quote_count": len(evidence_references),
        "retrieved_quote_count": len(evidence_references) - len(missing_references),
        "all_expected_quotes_retrieved": not missing_references,
        "missing_quotes": missing_references,
    }


def is_false_sufficient_status(*, actual_status: str, expected_status: str) -> bool:
    return actual_status == "sufficient" and expected_status != "sufficient"


def evaluate_case(
    *,
    case: dict[str, Any],
    assessor_gold: dict[str, Any],
    assessor: OllamaEvidenceAssessor,
    api_base_url: str,
    retrieval_timeout_seconds: float,
) -> dict[str, Any]:
    case_started = time.perf_counter()
    retrieval_started = time.perf_counter()
    retrieval_response = call_retrieval(
        api_base_url=api_base_url,
        question=case["question"],
        top_k=case["top_k"],
        timeout_seconds=retrieval_timeout_seconds,
    )
    chunks = parse_retrieved_chunks(retrieval_response["hits"], case_id=case["id"])
    retrieval_elapsed = time.perf_counter() - retrieval_started
    gold_evidence_metrics = gold_evidence_retrieval_metrics(
        assessor_gold=assessor_gold,
        chunks=chunks,
    )

    assessment_started = time.perf_counter()
    decision = assessor.assess(
        question=case["question"],
        retrieved_chunks=chunks,
    )
    assessment_elapsed = time.perf_counter() - assessment_started

    return {
        "id": case["id"],
        "question": case["question"],
        "expected": build_expected_result(case, assessor_gold),
        "retrieval": {
            **source_retrieval_metrics(
                expected_source_ids=case["expected_retrieval_source_ids"],
                chunks=chunks,
            ),
            "assessor_gold_evidence": gold_evidence_metrics,
            "elapsed_seconds": round(retrieval_elapsed, 3),
            "chunks": [serialize_chunk(chunk) for chunk in chunks],
        },
        "assessment": decision.model_dump(mode="json"),
        "checks": {
            "status_matches_expected": (
                decision.status == case["evidence_sufficiency"]
            ),
            "false_sufficient": is_false_sufficient_status(
                actual_status=decision.status,
                expected_status=case["evidence_sufficiency"],
            ),
            "gold_evidence_retrieved": (
                gold_evidence_metrics["all_expected_quotes_retrieved"]
            ),
            "assessment_contract_validation_passed": True,
        },
        "latency": {
            "retrieval_seconds": round(retrieval_elapsed, 3),
            "assessment_seconds": round(assessment_elapsed, 3),
            "case_total_seconds": round(time.perf_counter() - case_started, 3),
        },
        "manual_review": {
            "requested_information_coverage_correct": None,
            "answer_matches_evidence": None,
            "answer_is_declarative": None,
            "required_answer_facts_covered": None,
            "unsupported_claims_present": None,
            "recommended_action_appropriate": None,
            "notes": "",
        },
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    status_matches = [
        result["checks"]["status_matches_expected"]
        for result in results
        if isinstance(result.get("checks"), dict)
        and isinstance(result["checks"].get("status_matches_expected"), bool)
    ]
    retrieval_times = [
        result["latency"]["retrieval_seconds"]
        for result in results
        if isinstance(result.get("latency"), dict)
    ]
    assessment_times = [
        result["latency"]["assessment_seconds"]
        for result in results
        if isinstance(result.get("latency"), dict)
    ]
    source_recalls = [
        result["retrieval"]["source_recall_at_k"]
        for result in results
        if isinstance(result.get("retrieval"), dict)
        and isinstance(result["retrieval"].get("source_recall_at_k"), (int, float))
    ]
    evaluated_results = [
        result
        for result in results
        if isinstance(result.get("checks"), dict)
        and isinstance(result["checks"].get("false_sufficient"), bool)
    ]
    non_sufficient_results = [
        result
        for result in evaluated_results
        if result.get("expected", {}).get("evidence_sufficiency") != "sufficient"
    ]
    false_sufficient_ids = [
        result["id"]
        for result in non_sufficient_results
        if result["checks"]["false_sufficient"]
    ]
    gold_evidence_results = [
        result["retrieval"]["assessor_gold_evidence"]
        for result in results
        if isinstance(result.get("retrieval"), dict)
        and isinstance(result["retrieval"].get("assessor_gold_evidence"), dict)
    ]
    expected_gold_quotes = sum(
        evidence_result["expected_quote_count"]
        for evidence_result in gold_evidence_results
    )
    retrieved_gold_quotes = sum(
        evidence_result["retrieved_quote_count"]
        for evidence_result in gold_evidence_results
    )
    return {
        "cases_attempted": len(results),
        "status_evaluated_cases": len(status_matches),
        "status_matches": sum(status_matches),
        "status_match_rate": (
            round(sum(status_matches) / len(status_matches), 4)
            if status_matches
            else None
        ),
        "mean_source_recall_at_k": (
            round(statistics.mean(source_recalls), 4) if source_recalls else None
        ),
        "non_sufficient_cases_evaluated": len(non_sufficient_results),
        "false_sufficient_count": len(false_sufficient_ids),
        "false_sufficient_case_ids": false_sufficient_ids,
        "expected_gold_quote_count": expected_gold_quotes,
        "retrieved_gold_quote_count": retrieved_gold_quotes,
        "gold_quote_recall": (
            round(retrieved_gold_quotes / expected_gold_quotes, 4)
            if expected_gold_quotes
            else None
        ),
        "mean_retrieval_seconds": (
            round(statistics.mean(retrieval_times), 3) if retrieval_times else None
        ),
        "mean_assessment_seconds": (
            round(statistics.mean(assessment_times), 3) if assessment_times else None
        ),
    }


def save_artifact(
    *,
    repo_root: Path,
    dataset: Path,
    gold_dataset: Path,
    api_base_url: str,
    model_name: str,
    results: list[dict[str, Any]],
    run_error: str | None,
    run_elapsed_seconds: float,
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"evidence-assessor-pilot-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    artifact = {
        "evaluation": "evidence-assessor-pilot",
        "timestamp_utc": timestamp.isoformat(),
        "dataset": str(dataset),
        "assessor_gold_dataset": str(gold_dataset),
        "api_base_url": api_base_url.rstrip("/"),
        "assessor_model": model_name,
        "scope": (
            "Calls the retrieval endpoint and standalone evidence assessor. "
            "Does not call the support-draft endpoint or create a human-review task."
        ),
        "summary": {
            **summarize_results(results),
            "run_elapsed_seconds": round(run_elapsed_seconds, 3),
            "run_error": run_error,
        },
        "results": results,
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Could not write evaluation artifact {output_path}: {exc}", file=sys.stderr)
        raise
    return output_path


def print_summary(
    *,
    results: list[dict[str, Any]],
    artifact_path: Path,
    run_error: str | None,
) -> None:
    print("\nEvidence assessor pilot")
    print("case_id | expected | actual | status match | retrieval s | assessment s")
    print("-" * 90)
    for result in results:
        assessment = result.get("assessment")
        expected = result.get("expected", {}).get("evidence_sufficiency", "n/a")
        actual = assessment.get("status", "error") if isinstance(assessment, dict) else "error"
        checks = result.get("checks", {})
        match = checks.get("status_matches_expected", "n/a")
        latency = result.get("latency", {})
        retrieval_seconds = latency.get("retrieval_seconds", "n/a")
        assessment_seconds = latency.get("assessment_seconds", "n/a")
        print(
            f"{result['id']} | {expected} | {actual} | {match} | "
            f"{retrieval_seconds} | {assessment_seconds}"
        )

    summary = summarize_results(results)
    print(
        f"\nStatus matches: {summary['status_matches']}/"
        f"{summary['status_evaluated_cases']}"
    )
    print(
        "False-sufficient decisions: "
        f"{summary['false_sufficient_count']}/"
        f"{summary['non_sufficient_cases_evaluated']} non-sufficient cases"
    )
    if summary["false_sufficient_case_ids"]:
        print(
            "False-sufficient case IDs: "
            + ", ".join(summary["false_sufficient_case_ids"])
        )
    print(
        "Gold evidence quotes retrieved: "
        f"{summary['retrieved_gold_quote_count']}/"
        f"{summary['expected_gold_quote_count']} "
        f"(recall {summary['gold_quote_recall']})"
    )
    print(f"Mean retrieval time: {summary['mean_retrieval_seconds']} seconds")
    print(f"Mean assessor time: {summary['mean_assessment_seconds']} seconds")
    print(
        "Requested-information alignment, answer/fact correctness, and action fit "
        "still require manual review in the artifact."
    )
    if run_error:
        print(f"Run error: {run_error}")
    print(f"Artifact: {artifact_path}")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Run the five-case evidence-assessor pilot using real retrieval and Ollama."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=repo_root / "docs" / "evals" / "rag-week3-v1.jsonl",
        help="Path to the evaluation JSONL dataset.",
    )
    parser.add_argument(
        "--gold-dataset",
        type=Path,
        default=repo_root / "docs" / "evals" / "evidence-assessor-gold-v1.jsonl",
        help="Path to requested-information and evidence gold annotations.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://host.docker.internal:8000",
        help="Base URL for the running retrieval API.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300,
        help="Maximum wait for each retrieval API call.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run a specific case ID; repeat this flag to run multiple cases.",
    )
    parser.add_argument(
        "--all-cases",
        action="store_true",
        help="Run every case in the dataset instead of the five-case pilot.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Artifact path (default: docs/evals/results/evidence-assessor-pilot-<UTC>.json).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout_seconds <= 0:
        print("--timeout-seconds must be greater than zero.", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    dataset = args.dataset if args.dataset.is_absolute() else repo_root / args.dataset
    gold_dataset = (
        args.gold_dataset
        if args.gold_dataset.is_absolute()
        else repo_root / args.gold_dataset
    )
    try:
        cases = load_cases(dataset, REQUIRED_FIELDS)
        for case in cases:
            validate_case(case)
        assessor_gold_by_id = load_assessor_gold(gold_dataset, cases)
        selected_cases = select_cases(
            cases,
            case_ids=args.case_ids,
            all_cases=args.all_cases,
        )
    except DatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    settings = get_settings()
    provider = OllamaLLMProvider(
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    assessor = OllamaEvidenceAssessor(
        generator=provider,
        model_name=settings.evidence_assessor_model,
    )

    results: list[dict[str, Any]] = []
    run_error = None
    run_started = time.perf_counter()
    for case in selected_cases:
        try:
            results.append(
                evaluate_case(
                    case=case,
                    assessor_gold=assessor_gold_by_id[case["id"]],
                    assessor=assessor,
                    api_base_url=args.api_base_url,
                    retrieval_timeout_seconds=args.timeout_seconds,
                )
            )
        except (RetrievalAPIError, EvidenceAssessorError) as exc:
            run_error = f"{case['id']}: {exc}"
            results.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "expected": build_expected_result(
                        case,
                        assessor_gold_by_id[case["id"]],
                    ),
                    "error": str(exc),
                }
            )
            break
    run_elapsed = time.perf_counter() - run_started

    try:
        artifact_path = save_artifact(
            repo_root=repo_root,
            dataset=dataset,
            gold_dataset=gold_dataset,
            api_base_url=args.api_base_url,
            model_name=settings.evidence_assessor_model,
            results=results,
            run_error=run_error,
            run_elapsed_seconds=run_elapsed,
            output_path=args.output,
        )
    except OSError:
        return 2

    print_summary(
        results=results,
        artifact_path=artifact_path,
        run_error=run_error,
    )
    if run_error:
        return 3
    return 0 if all(
        result["checks"]["status_matches_expected"]
        and result["checks"]["gold_evidence_retrieved"]
        for result in results
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
