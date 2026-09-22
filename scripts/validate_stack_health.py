import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request


REQUIRED_SERVICES = ["postgres", "redis", "ollama", "pgadmin", "api"]
REQUIRED_PORTS = {
    "postgres": 5432,
    "redis": 6379,
    "ollama": 11434,
    "pgadmin": 5050,
    "api": 8000,
}


def read_compose_ps() -> list[dict]:
    proc = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "docker compose ps failed")

    output = proc.stdout.strip()
    if not output:
        return []

    if output.startswith("["):
        return json.loads(output)

    rows: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def service_name(row: dict) -> str:
    svc = row.get("Service")
    if svc:
        return svc
    name = row.get("Name", "")
    parts = name.split("-")
    if len(parts) >= 2:
        return parts[-2]
    return name


def check_compose_services(results: list[str]) -> bool:
    ok = True
    rows = read_compose_ps()
    by_service = {service_name(r): r for r in rows}

    for svc in REQUIRED_SERVICES:
        row = by_service.get(svc)
        if row is None:
            results.append(f"[FAIL] service missing in compose ps: {svc}")
            ok = False
            continue

        state = str(row.get("State", "")).lower()
        health = str(row.get("Health", "")).lower()

        if state not in {"running", "up"}:
            results.append(f"[FAIL] service state not running: {svc} state={state}")
            ok = False
        else:
            results.append(f"[PASS] service running: {svc}")

        if health and health != "healthy":
            results.append(f"[FAIL] service health not healthy: {svc} health={health}")
            ok = False
        elif health:
            results.append(f"[PASS] service healthy: {svc}")

    return ok


def check_port(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        return sock.connect_ex((host, port)) == 0


def check_ports(results: list[str]) -> bool:
    ok = True
    for svc, port in REQUIRED_PORTS.items():
        if check_port("127.0.0.1", port):
            results.append(f"[PASS] port open: {svc} -> {port}")
        else:
            results.append(f"[FAIL] port closed: {svc} -> {port}")
            ok = False
    return ok


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def http_status(url: str) -> int:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.getcode()


def check_http(results: list[str]) -> bool:
    ok = True

    # API health
    try:
        payload = http_json("http://localhost:8000/health")
        if payload.get("status") == "ok":
            results.append("[PASS] api health endpoint returned status=ok")
        else:
            results.append(f"[FAIL] api health payload unexpected: {payload}")
            ok = False
    except Exception as exc:
        results.append(f"[FAIL] api health request failed: {exc}")
        ok = False

    # Ollama
    try:
        status = http_status("http://localhost:11434/api/tags")
        if status == 200:
            results.append("[PASS] ollama /api/tags reachable")
        else:
            results.append(f"[FAIL] ollama /api/tags status={status}")
            ok = False
    except Exception as exc:
        results.append(f"[FAIL] ollama request failed: {exc}")
        ok = False

    # pgAdmin (200 or redirect expected)
    try:
        status = http_status("http://localhost:5050/")
        if status in {200, 301, 302, 303, 307, 308}:
            results.append(f"[PASS] pgadmin reachable status={status}")
        else:
            results.append(f"[FAIL] pgadmin unexpected status={status}")
            ok = False
    except Exception as exc:
        results.append(f"[FAIL] pgadmin request failed: {exc}")
        ok = False

    return ok


def main() -> int:
    results: list[str] = []
    all_ok = True

    try:
        if not check_compose_services(results):
            all_ok = False
    except Exception as exc:
        results.append(f"[FAIL] compose service check failed: {exc}")
        all_ok = False

    if not check_ports(results):
        all_ok = False

    if not check_http(results):
        all_ok = False

    print("\nStack Health Check Results\n")
    for line in results:
        print(line)

    print("\nSummary")
    print(f"- status: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())