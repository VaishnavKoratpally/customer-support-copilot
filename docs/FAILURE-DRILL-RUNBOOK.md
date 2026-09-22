# Failure Drill Runbook (Day 6)

## Purpose
Validate that our observability checks detect dependency failure and confirm recovery.

## Drill scenario
Simulate Redis outage, verify health check failure, then restore Redis and verify recovery.

## Command
```powershell
python scripts/run_failure_drill.py