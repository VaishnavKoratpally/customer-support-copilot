import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "http://localhost:8000"
DRAFT_REQUEST_TIMEOUT_SECONDS = 300


def run_command(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def http_json(url: str) -> dict:
    req = Request(url, method="GET")
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_draft_cases(path: Path) -> list[dict]:
    cases = []
    seen_ids = set()

    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            case = json.loads(line)
            if not isinstance(case, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")

            case_id = case.get("id")
            question = case.get("question")
            customer_tier = case.get("customer_tier")

            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{path}:{line_number}: missing string id")
            if case_id in seen_ids:
                raise ValueError(f"{path}:{line_number}: duplicate id {case_id}")
            if not isinstance(question, str) or len(question) < 5:
                raise ValueError(f"{path}:{line_number}: invalid question")
            if customer_tier not in {"free", "pro", "enterprise"}:
                raise ValueError(f"{path}:{line_number}: invalid customer_tier")

            seen_ids.add(case_id)
            cases.append(case)

    if not cases:
        raise ValueError(f"No draft traffic cases found in {path}")

    return cases


def post_support_draft(case: dict, run_id: str) -> dict:
    payload = {
        "question": case["question"],
        "ticket_id": f"baseline-{run_id}-{case['id']}",
        "customer_tier": case["customer_tier"],
    }
    req = Request(
        f"{API_BASE_URL}/v1/support/draft",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    status_code = None
    trace_id = None
    error = None

    try:
        with urlopen(req, timeout=DRAFT_REQUEST_TIMEOUT_SECONDS) as resp:
            status_code = resp.status
            try:
                response_body = json.loads(resp.read().decode("utf-8"))
            except json.JSONDecodeError:
                error = "Response body was not valid JSON"
            else:
                if not isinstance(response_body, dict):
                    error = "Response JSON was not an object"
                else:
                    trace_id = response_body.get("trace_id")
                    if not isinstance(trace_id, str) or not trace_id:
                        error = "Response was missing trace_id"
    except HTTPError as exc:
        status_code = exc.code
        exc.close()
        error = f"HTTP {status_code}"
    except (URLError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    success = status_code == 200 and trace_id is not None and error is None

    return {
        "case_id": case["id"],
        "status_code": status_code,
        "client_duration_ms": duration_ms,
        "trace_id": trace_id,
        "success": success,
        "error": error,
    }


def run_support_draft_traffic(cases: list[dict], run_id: str) -> list[dict]:
    results = []

    for case in cases:
        result = post_support_draft(case, run_id)
        results.append(result)

        status = result["status_code"]
        if result["success"]:
            print(f"Draft {case['id']}: HTTP {status}, {result['client_duration_ms']} ms")
        else:
            print(
                f"Draft {case['id']} failed: "
                f"status={status}, error={result['error']}"
            )

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generate-support-draft-traffic",
        action="store_true",
        help="Send the fixed synthetic draft workload before capturing metrics.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = repo_root / "docs" / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    git_sha_proc = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    git_sha = git_sha_proc.stdout.strip() if git_sha_proc.returncode == 0 else "unknown"

    draft_traffic_results = []
    draft_dataset = None
    preflight_draft_metrics = None

    if args.generate_support_draft_traffic:
        draft_dataset = repo_root / "docs" / "evals" / "support-draft-traffic-v1.jsonl"
        preflight_metrics = http_json(f"{API_BASE_URL}/v1/metrics")

        required_metrics = {
            "support_draft_total",
            "support_draft_request_total",
            "support_draft_request_latency_p95_ms",
        }
        missing_metrics = required_metrics.difference(preflight_metrics)
        if missing_metrics:
            raise RuntimeError(
                "API is missing route-specific support-draft metrics. "
                "Rebuild the API before running the baseline."
            )

        preflight_draft_metrics = {
            "support_draft_total": preflight_metrics["support_draft_total"],
            "support_draft_request_total": preflight_metrics[
                "support_draft_request_total"
            ],
        }
        if any(preflight_draft_metrics.values()):
            raise RuntimeError(
                "Support-draft metrics are not fresh. Restart/rebuild the API "
                "so this baseline starts with zero draft requests."
            )

        cases = load_draft_cases(draft_dataset)
        draft_traffic_results = run_support_draft_traffic(cases, timestamp)

    retrieval_proc = run_command(
        [sys.executable, "scripts/retrieval_smoke_eval.py"],
        cwd=repo_root,
    )

    metrics_payload = {}
    metrics_error = None
    try:
        metrics_payload = http_json(f"{API_BASE_URL}/v1/metrics")
    except Exception as exc:
        metrics_error = str(exc)

    successful_drafts = sum(result["success"] for result in draft_traffic_results)
    draft_traffic = {
        "enabled": args.generate_support_draft_traffic,
        "dataset": (
            str(draft_dataset.relative_to(repo_root))
            if draft_dataset is not None
            else None
        ),
        "preflight_metrics": preflight_draft_metrics,
        "attempted": len(draft_traffic_results),
        "successful": successful_drafts,
        "failed": len(draft_traffic_results) - successful_drafts,
        "results": draft_traffic_results,
    }

    baseline = {
        "timestamp_utc": timestamp,
        "git_sha": git_sha,
        "support_draft_traffic": draft_traffic,
        "retrieval_smoke": {
            "exit_code": retrieval_proc.returncode,
            "stdout": retrieval_proc.stdout,
            "stderr": retrieval_proc.stderr,
        },
        "service_metrics": {
            "payload": metrics_payload,
            "error": metrics_error,
        },
    }

    out_file = out_dir / f"baseline-{timestamp}.json"
    out_file.write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    print(f"Baseline artifact saved: {out_file}")
    print(f"Support draft traffic: {successful_drafts}/{len(draft_traffic_results)} succeeded")
    print(f"Retrieval smoke exit code: {retrieval_proc.returncode}")

    if metrics_error:
        print(f"Metrics fetch error: {metrics_error}")
        return 1

    if draft_traffic["failed"]:
        print("One or more support-draft requests failed; inspect the artifact.")
        return 1

    print("Metrics snapshot captured successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())