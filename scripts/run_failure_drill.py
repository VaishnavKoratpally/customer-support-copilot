import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")
    return proc


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    validator = [sys.executable, "scripts/validate_stack_health.py"]

    print("=== Failure Drill: Simulate Redis outage and recovery ===")
    print("Step 1: stop redis")
    run(["docker", "compose", "stop", "redis"], cwd=repo_root)

    try:
        print("Step 2: run health validator (expected to FAIL)")
        failed_check = subprocess.run(validator, cwd=repo_root, text=True)
        if failed_check.returncode == 0:
            print("FAIL: validator unexpectedly passed while redis is stopped.")
            return 1
        print("PASS: validator failed as expected during outage.")
    finally:
        print("Step 3: restart redis")
        run(["docker", "compose", "start", "redis"], cwd=repo_root)

    print("Step 4: wait for recovery")
    recovered = False
    for _ in range(12):
        check = subprocess.run(validator, cwd=repo_root, text=True)
        if check.returncode == 0:
            recovered = True
            break
        time.sleep(5)

    if not recovered:
        print("FAIL: stack did not recover to healthy state in time.")
        return 2

    print("PASS: stack recovered and validator passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())