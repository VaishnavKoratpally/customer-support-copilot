import argparse
import json
import math
import sys
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_RECALL_TARGET = 0.75


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


def evaluate_case(case: dict, response: dict, *, top_k: int) -> dict:
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
        "top_k": top_k,
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


def summarize_results(results: list[dict]) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for top_k in sorted({result["top_k"] for result in results}):
        top_k_results = [result for result in results if result["top_k"] == top_k]
        scored_results = [
            result for result in top_k_results if result["recall_at_k"] is not None
        ]
        average_recall = (
            sum(result["recall_at_k"] for result in scored_results)
            / len(scored_results)
            if scored_results
            else None
        )
        precision_results = [
            result
            for result in scored_results
            if result["source_precision_at_k"] is not None
        ]
        average_precision = (
            sum(result["source_precision_at_k"] for result in precision_results)
            / len(precision_results)
            if precision_results
            else None
        )
        summaries[str(top_k)] = {
            "total_cases": len(top_k_results),
            "cases_with_expected_sources": len(scored_results),
            "cases_without_expected_sources": len(top_k_results) - len(scored_results),
            "mean_source_recall_at_k": (
                round(average_recall, 4) if average_recall is not None else None
            ),
            "mean_unique_source_precision_at_k": (
                round(average_precision, 4)
                if average_precision is not None
                else None
            ),
            "source_recall_target": SOURCE_RECALL_TARGET,
            "source_recall_target_met": (
                average_recall >= SOURCE_RECALL_TARGET
                if average_recall is not None
                else None
            ),
        }
    return summaries


def save_artifact(
    *,
    repo_root: Path,
    dataset: Path,
    api_base_url: str,
    results: list[dict],
    warm_up_requests: int,
    output_path: Path | None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    if output_path is None:
        output_path = (
            repo_root
            / "docs"
            / "evals"
            / "results"
            / f"retrieval-smoke-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    elif not output_path.is_absolute():
        output_path = repo_root / output_path

    artifact = {
        "evaluation": "week3-vector-retrieval",
        "timestamp_utc": timestamp.isoformat(),
        "dataset": str(dataset),
        "api_base_url": api_base_url.rstrip("/"),
        "warm_up_requests": warm_up_requests,
        "top_k_values": sorted({result["top_k"] for result in results}),
        "metric_unit": "unique source IDs, not individual chunks",
        "source_recall_target": SOURCE_RECALL_TARGET,
        "summary_by_top_k": summarize_results(results),
        "results": results,
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(artifact, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Could not write evaluation artifact {output_path}: {exc}",
            file=sys.stderr,
        )
        raise
    return output_path


def print_results(results: list[dict], *, artifact_path: Path) -> None:
    print("\nWeek 3 Vector Retrieval Diagnostic\n")
    print("id                                   | k | Recall@k | Source P@k | other sources       | nearest distance")
    print("-" * 116)
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
            f"{result['top_k']:<1} | "
            f"{recall:<8} | "
            f"{precision:<10} | "
            f"{','.join(result['non_expected_source_ids']) or '-':<20} | "
            f"{distance}"
        )

    print("\nSummary")
    for top_k, summary in summarize_results(results).items():
        recall = summary["mean_source_recall_at_k"]
        precision = summary["mean_unique_source_precision_at_k"]
        target_met = summary["source_recall_target_met"]
        print(
            f"- k={top_k}: source Recall@k="
            f"{recall if recall is not None else 'n/a'}, "
            "unique-source precision@k="
            f"{precision if precision is not None else 'n/a'}, "
            f"recall target met={target_met if target_met is not None else 'n/a'}"
        )
        print(
            f"  Cases with expected sources: {summary['cases_with_expected_sources']}; "
            f"without expected sources: {summary['cases_without_expected_sources']}"
        )
    print("- Precision/recall use unique source IDs, not individual chunk hits.")
    print("- No evidence cutoff is applied; nearest distances and other sources are diagnostic only.")
    print(f"Artifact: {artifact_path}")


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
    parser.add_argument(
        "--top-k-values",
        type=int,
        nargs="+",
        metavar="K",
        help=(
            "Compare these top-k values on every case, changing only k. "
            "By default, each case uses its dataset top_k."
        ),
    )
    parser.add_argument(
        "--warm-up",
        action="store_true",
        help=(
            "Make one unscored request using the first case before collecting "
            "measurements, to warm the embedding model."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Artifact path (default: docs/evals/results/"
            "retrieval-smoke-<UTC timestamp>.json)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dataset = args.dataset if args.dataset.is_absolute() else repo_root / args.dataset

    if not dataset.exists():
        print(f"Dataset file not found: {dataset}", file=sys.stderr)
        return 2

    try:
        cases = load_cases(dataset)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.top_k_values is not None:
        if not args.top_k_values:
            print("--top-k-values must include at least one value.", file=sys.stderr)
            return 2
        if len(set(args.top_k_values)) != len(args.top_k_values):
            print("--top-k-values must not contain duplicates.", file=sys.stderr)
            return 2
        if any(top_k < 1 for top_k in args.top_k_values):
            print("Each --top-k-values entry must be at least 1.", file=sys.stderr)
            return 2

    results: list[dict] = []
    warm_up_requests = 0
    try:
        if args.warm_up:
            first_case = cases[0]
            first_top_k = (
                args.top_k_values[0]
                if args.top_k_values is not None
                else first_case.get("top_k")
            )
            if (
                isinstance(first_top_k, bool)
                or not isinstance(first_top_k, int)
                or first_top_k < 1
            ):
                raise ValueError(
                    f"Case {first_case.get('id', '<unknown>')} must define top_k "
                    "as a positive integer for warm-up."
                )
            first_question = first_case.get("question")
            if not isinstance(first_question, str) or not first_question.strip():
                raise ValueError(
                    f"Case {first_case.get('id', '<unknown>')} must define a non-empty question."
                )
            call_retrieval(
                api_base_url=args.api_base_url,
                question=first_question,
                top_k=first_top_k,
            )
            warm_up_requests = 1

        for case in cases:
            case_top_k = case.get("top_k")
            if (
                isinstance(case_top_k, bool)
                or not isinstance(case_top_k, int)
                or case_top_k < 1
            ):
                raise ValueError(
                    f"Case {case.get('id', '<unknown>')} must define top_k "
                    "as a positive integer."
                )
            top_k_values = args.top_k_values or [case_top_k]
            for top_k in top_k_values:
                response = call_retrieval(
                    api_base_url=args.api_base_url,
                    question=case["question"],
                    top_k=top_k,
                )
                results.append(evaluate_case(case, response, top_k=top_k))
    except urllib.error.HTTPError as exc:
        print(f"HTTP error from API: {exc.code} {exc.reason}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {args.api_base_url}: {exc.reason}", file=sys.stderr)
        return 3
    except (KeyError, TypeError, ValueError) as exc:
        print(f"Invalid evaluation data or API response: {exc}", file=sys.stderr)
        return 2

    try:
        artifact_path = save_artifact(
            repo_root=repo_root,
            dataset=dataset,
            api_base_url=args.api_base_url,
            results=results,
            warm_up_requests=warm_up_requests,
            output_path=args.output,
        )
    except OSError:
        return 2

    print_results(results, artifact_path=artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
