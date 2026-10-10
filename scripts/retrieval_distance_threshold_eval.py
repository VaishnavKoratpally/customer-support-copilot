import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_utils import load_cases


def read_retrieval_artifact(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read retrieval artifact {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in retrieval artifact {path}: {exc}") from exc

    if not isinstance(artifact, dict):
        raise ValueError("Retrieval artifact must be a JSON object.")
    return artifact


def build_case_rows(
    dataset_cases: list[dict[str, Any]],
    retrieval_artifact: dict[str, Any],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    artifact_results = retrieval_artifact.get("results")
    if not isinstance(artifact_results, list):
        raise ValueError("Retrieval artifact must contain a results array.")

    dataset_by_id: dict[str, dict[str, Any]] = {}
    for case in dataset_cases:
        case_id = case.get("id")
        expected_source_ids = case.get("expected_retrieval_source_ids")
        evidence_sufficiency = case.get("evidence_sufficiency")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Every dataset case must have a non-empty string id.")
        if not isinstance(expected_source_ids, list) or any(
            not isinstance(source_id, str) for source_id in expected_source_ids
        ):
            raise ValueError(
                f"Case {case_id} must define expected_retrieval_source_ids "
                "as a string array."
            )
        if not isinstance(evidence_sufficiency, str) or not evidence_sufficiency:
            raise ValueError(
                f"Case {case_id} must define evidence_sufficiency as a string."
            )
        if case_id in dataset_by_id:
            raise ValueError(f"Dataset contains duplicate case id {case_id!r}.")
        dataset_by_id[case_id] = case

    results_by_id: dict[str, dict[str, Any]] = {}
    for result in artifact_results:
        if not isinstance(result, dict):
            raise ValueError("Retrieval artifact contains a malformed result row.")
        result_top_k = result.get("top_k")
        if isinstance(result_top_k, bool) or not isinstance(result_top_k, int):
            raise ValueError("Retrieval artifact result rows must define integer top_k.")
        if result_top_k != top_k:
            continue

        case_id = result.get("id")
        expected_source_ids = result.get("expected_source_ids")
        distance = result.get("nearest_cosine_distance")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Retrieval artifact result rows must define a non-empty id.")
        if not isinstance(expected_source_ids, list) or any(
            not isinstance(source_id, str) for source_id in expected_source_ids
        ):
            raise ValueError(
                f"Retrieval artifact case {case_id} must define expected_source_ids "
                "as a string array."
            )
        if distance is not None and (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not math.isfinite(distance)
        ):
            raise ValueError(
                f"Retrieval artifact case {case_id} has an invalid nearest cosine distance."
            )
        if case_id in results_by_id:
            raise ValueError(
                f"Retrieval artifact contains duplicate case {case_id!r} for top_k={top_k}."
            )
        results_by_id[case_id] = result

    if not results_by_id:
        raise ValueError(f"Retrieval artifact has no results for top_k={top_k}.")
    if results_by_id.keys() != dataset_by_id.keys():
        missing = sorted(dataset_by_id.keys() - results_by_id.keys())
        unexpected = sorted(results_by_id.keys() - dataset_by_id.keys())
        raise ValueError(
            f"Dataset/artifact case IDs do not match for top_k={top_k}; "
            f"missing results={missing}, unexpected results={unexpected}."
        )

    rows: list[dict[str, Any]] = []
    for case_id, case in dataset_by_id.items():
        expected_source_ids = set(case["expected_retrieval_source_ids"])
        artifact_source_ids = set(results_by_id[case_id]["expected_source_ids"])
        if expected_source_ids != artifact_source_ids:
            raise ValueError(
                f"Dataset/artifact expected-source labels differ for case {case_id}."
            )
        rows.append(
            {
                "id": case_id,
                "top_k": top_k,
                "nearest_cosine_distance": results_by_id[case_id][
                    "nearest_cosine_distance"
                ],
                "expected_source_ids": sorted(expected_source_ids),
                "expected_source_present": bool(expected_source_ids),
                "evidence_sufficiency": case["evidence_sufficiency"],
            }
        )
    return rows


def threshold_candidates(rows: list[dict[str, Any]]) -> list[float]:
    distances = sorted(
        {
            row["nearest_cosine_distance"]
            for row in rows
            if row["nearest_cosine_distance"] is not None
        }
    )
    if not distances:
        raise ValueError("Cannot sweep thresholds because the selected cases have no hits.")

    candidates = [math.nextafter(distances[0], -math.inf)]
    candidates.extend(
        (left + right) / 2 for left, right in zip(distances, distances[1:])
    )
    candidates.append(math.nextafter(distances[-1], math.inf))
    return candidates


def score_threshold(
    rows: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    if not math.isfinite(threshold):
        raise ValueError("Threshold must be finite.")

    true_source_present = 0
    false_source_present = 0
    true_source_absent = 0
    false_source_absent = 0
    for row in rows:
        distance = row["nearest_cosine_distance"]
        predicted_source_present = (
            distance is not None and distance <= threshold
        )
        if row["expected_source_present"] and predicted_source_present:
            true_source_present += 1
        elif not row["expected_source_present"] and predicted_source_present:
            false_source_present += 1
        elif not row["expected_source_present"]:
            true_source_absent += 1
        else:
            false_source_absent += 1

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    source_presence_recall = ratio(
        true_source_present,
        true_source_present + false_source_absent,
    )
    no_source_detection_recall = ratio(
        true_source_absent,
        true_source_absent + false_source_present,
    )
    balanced_accuracy = (
        round((source_presence_recall + no_source_detection_recall) / 2, 4)
        if source_presence_recall is not None
        and no_source_detection_recall is not None
        else None
    )

    return {
        "threshold": threshold,
        "confusion_matrix": {
            "true_source_present": true_source_present,
            "false_source_present": false_source_present,
            "true_source_absent": true_source_absent,
            "false_source_absent": false_source_absent,
        },
        "metrics": {
            "source_presence_precision": ratio(
                true_source_present,
                true_source_present + false_source_present,
            ),
            "source_presence_recall": source_presence_recall,
            "no_source_detection_recall": no_source_detection_recall,
            "false_accept_rate": ratio(
                false_source_present,
                false_source_present + true_source_absent,
            ),
            "false_reject_rate": ratio(
                false_source_absent,
                false_source_absent + true_source_present,
            ),
            "balanced_accuracy": balanced_accuracy,
            "accuracy": ratio(
                true_source_present + true_source_absent,
                len(rows),
            ),
        },
    }


def evaluate_thresholds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        score_threshold(rows, threshold)
        for threshold in threshold_candidates(rows)
    ]


def save_artifact(
    *,
    repo_root: Path,
    input_artifact_path: Path,
    input_artifact: dict[str, Any],
    dataset_path: Path,
    top_k: int,
    rows: list[dict[str, Any]],
    threshold_results: list[dict[str, Any]],
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"retrieval-distance-threshold-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    sufficiency_counts: dict[str, int] = {}
    for row in rows:
        status = row["evidence_sufficiency"]
        sufficiency_counts[status] = sufficiency_counts.get(status, 0) + 1
    artifact = {
        "evaluation": "retrieval-distance-threshold-diagnostic",
        "timestamp_utc": timestamp.isoformat(),
        "input_retrieval_artifact": str(input_artifact_path),
        "input_warm_up_requests": input_artifact.get("warm_up_requests"),
        "dataset": str(dataset_path),
        "top_k": top_k,
        "label_semantics": {
            "source_present": (
                "The dataset has at least one expected_retrieval_source_id."
            ),
            "threshold_prediction": (
                "A source is predicted present when nearest cosine distance "
                "is less than or equal to the threshold."
            ),
            "not_answerability": (
                "Expected source presence does not mean that source contains "
                "enough evidence to answer the request."
            ),
        },
        "sample_summary": {
            "total_cases": len(rows),
            "cases_with_expected_sources": sum(
                row["expected_source_present"] for row in rows
            ),
            "cases_without_expected_sources": sum(
                not row["expected_source_present"] for row in rows
            ),
            "evidence_sufficiency_counts": sufficiency_counts,
        },
        "threshold_results": threshold_results,
        "cases": rows,
        "limitations": [
            "Thresholds are evaluated on this same small labeled set; no holdout set is used.",
            "Only cases with no expected retrieval source count as negatives.",
            "This does not assess claim support, evidence sufficiency, or answerability.",
            "This diagnostic does not select or enforce a production cutoff.",
        ],
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(artifact, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Could not write threshold evaluation artifact {output_path}: {exc}",
            file=sys.stderr,
        )
        raise
    return output_path


def print_results(
    rows: list[dict[str, Any]],
    threshold_results: list[dict[str, Any]],
    *,
    input_artifact_path: Path,
    output_artifact_path: Path,
    warm_up_requests: Any,
) -> None:
    print("\nCosine Distance Cutoff Diagnostic")
    print(
        f"- Cases: {len(rows)}; expected source present: "
        f"{sum(row['expected_source_present'] for row in rows)}; "
        f"no expected source: {sum(not row['expected_source_present'] for row in rows)}"
    )
    print(f"- Warm-up requests in retrieval run: {warm_up_requests}")
    print(
        "threshold | source recall | no-source recall | false accept | "
        "false reject | balanced accuracy"
    )
    print("-" * 86)
    for result in threshold_results:
        metrics = result["metrics"]

        def format_metric(value: float | None) -> str:
            return f"{value:.3f}" if value is not None else "n/a"

        print(
            f"{result['threshold']:.6f} | "
            f"{format_metric(metrics['source_presence_recall']):<13} | "
            f"{format_metric(metrics['no_source_detection_recall']):<16} | "
            f"{format_metric(metrics['false_accept_rate']):<12} | "
            f"{format_metric(metrics['false_reject_rate']):<12} | "
            f"{format_metric(metrics['balanced_accuracy'])}"
        )
    print(
        "\nThis predicts whether a labeled relevant source exists, not whether "
        "the retrieved text answers the user's question."
    )
    print(
        "No cutoff is selected: the sweep is in-sample, with only "
        f"{sum(not row['expected_source_present'] for row in rows)} negative cases."
    )
    print(f"Input retrieval artifact: {input_artifact_path}")
    print(f"Artifact: {output_artifact_path}")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Sweep offline cosine-distance cutoffs for expected-source presence; "
            "this does not assess answerability."
        )
    )
    parser.add_argument(
        "--retrieval-artifact",
        type=Path,
        required=True,
        help="Retrieval-smoke JSON artifact to analyze.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=repo_root / "docs" / "evals" / "rag-week3-v1.jsonl",
        help="Labeled Week 3 retrieval JSONL dataset.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=1,
        help="Analyze exactly one result per case at this top_k (default: 1).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Artifact path (default: docs/evals/results/"
            "retrieval-distance-threshold-<UTC timestamp>.json)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    input_artifact_path = (
        args.retrieval_artifact
        if args.retrieval_artifact.is_absolute()
        else repo_root / args.retrieval_artifact
    )
    dataset_path = args.dataset if args.dataset.is_absolute() else repo_root / args.dataset

    if args.top_k < 1:
        print("--top-k must be at least 1.", file=sys.stderr)
        return 2

    try:
        input_artifact = read_retrieval_artifact(input_artifact_path)
        dataset_cases = load_cases(
            dataset_path,
            required_fields={"expected_retrieval_source_ids", "evidence_sufficiency"},
        )
        rows = build_case_rows(
            dataset_cases,
            input_artifact,
            top_k=args.top_k,
        )
        threshold_results = evaluate_thresholds(rows)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        output_artifact_path = save_artifact(
            repo_root=repo_root,
            input_artifact_path=input_artifact_path,
            input_artifact=input_artifact,
            dataset_path=dataset_path,
            top_k=args.top_k,
            rows=rows,
            threshold_results=threshold_results,
            output_path=args.output,
        )
    except OSError:
        return 2

    print_results(
        rows,
        threshold_results,
        input_artifact_path=input_artifact_path,
        output_artifact_path=output_artifact_path,
        warm_up_requests=input_artifact.get("warm_up_requests", "not recorded"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
