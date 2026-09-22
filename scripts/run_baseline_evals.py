import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def run_command(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def http_json(url: str) -> dict:
    req = Request(url, method="GET")
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = repo_root / "docs" / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    git_sha_proc = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    git_sha = git_sha_proc.stdout.strip() if git_sha_proc.returncode == 0 else "unknown"

    retrieval_proc = run_command(
        [sys.executable, "scripts/retrieval_smoke_eval.py"],
        cwd=repo_root,
    )

    metrics_payload = {}
    metrics_error = None
    try:
        metrics_payload = http_json("http://localhost:8000/v1/metrics")
    except Exception as exc:
        metrics_error = str(exc)

    baseline = {
        "timestamp_utc": timestamp,
        "git_sha": git_sha,
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
    print(f"Retrieval smoke exit code: {retrieval_proc.returncode}")
    if metrics_error:
        print(f"Metrics fetch error: {metrics_error}")
        return 1

    print("Metrics snapshot captured successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())