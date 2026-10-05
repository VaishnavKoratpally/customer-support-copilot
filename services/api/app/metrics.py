from threading import Lock


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((percentile / 100.0) * (len(sorted_values) - 1)))
    return round(sorted_values[index], 2)


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = Lock()

        self._request_total = 0
        self._request_error_total = 0
        self._request_latency_ms: list[float] = []

        self._support_draft_request_total = 0
        self._support_draft_request_error_total = 0
        self._support_draft_request_latency_ms: list[float] = []

        self._support_draft_total = 0
        self._support_human_review_total = 0

    def record_http_request(
        self, *, path: str, status_code: int, duration_ms: float
    ) -> None:
        with self._lock:
            self._request_total += 1
            if status_code >= 500:
                self._request_error_total += 1

            self._request_latency_ms.append(round(duration_ms, 2))
            if len(self._request_latency_ms) > 5000:
                self._request_latency_ms.pop(0)

            if path == "/v1/support/draft":
                self._support_draft_request_total += 1
                if status_code >= 500:
                    self._support_draft_request_error_total += 1

                self._support_draft_request_latency_ms.append(round(duration_ms, 2))
                if len(self._support_draft_request_latency_ms) > 5000:
                    self._support_draft_request_latency_ms.pop(0)

    def record_support_draft(self, *, requires_human_review: bool) -> None:
        with self._lock:
            self._support_draft_total += 1
            if requires_human_review:
                self._support_human_review_total += 1

    def snapshot(self) -> dict:
        with self._lock:
            request_total = self._request_total
            request_error_total = self._request_error_total
            support_draft_request_total = self._support_draft_request_total
            support_draft_request_error_total = (
                self._support_draft_request_error_total
            )
            support_draft_total = self._support_draft_total
            support_human_review_total = self._support_human_review_total
            latencies = list(self._request_latency_ms)
            support_draft_latencies = list(
                self._support_draft_request_latency_ms
            )

        error_rate = (request_error_total / request_total) if request_total else 0.0
        support_draft_request_error_rate = (
            support_draft_request_error_total / support_draft_request_total
            if support_draft_request_total
            else 0.0
        )
        escalation_rate = (
            support_human_review_total / support_draft_total
            if support_draft_total
            else 0.0
        )

        return {
            "request_total": request_total,
            "request_error_total": request_error_total,
            "request_error_rate": round(error_rate, 4),
            "request_latency_p50_ms": _percentile(latencies, 50),
            "request_latency_p95_ms": _percentile(latencies, 95),
            "support_draft_request_total": support_draft_request_total,
            "support_draft_request_error_total": support_draft_request_error_total,
            "support_draft_request_error_rate": round(
                support_draft_request_error_rate, 4
            ),
            "support_draft_request_latency_p50_ms": _percentile(
                support_draft_latencies, 50
            ),
            "support_draft_request_latency_p95_ms": _percentile(
                support_draft_latencies, 95
            ),
            "support_draft_total": support_draft_total,
            "support_human_review_total": support_human_review_total,
            "support_human_review_rate": round(escalation_rate, 4),
        }