import unittest

from app.metrics import InMemoryMetrics


class InMemoryMetricsTests(unittest.TestCase):
    def test_support_draft_metrics_are_route_specific(self):
        metrics = InMemoryMetrics()

        metrics.record_http_request(
            path="/v1/retrieval/query",
            status_code=200,
            duration_ms=10000,
        )
        metrics.record_http_request(
            path="/v1/support/draft",
            status_code=200,
            duration_ms=120,
        )
        metrics.record_http_request(
            path="/v1/support/draft",
            status_code=502,
            duration_ms=500,
        )
        metrics.record_support_draft(requires_human_review=True)

        snapshot = metrics.snapshot()

        self.assertEqual(snapshot["request_total"], 3)
        self.assertEqual(snapshot["request_latency_p95_ms"], 10000)
        self.assertEqual(snapshot["support_draft_request_total"], 2)
        self.assertEqual(snapshot["support_draft_request_error_total"], 1)
        self.assertEqual(snapshot["support_draft_request_error_rate"], 0.5)
        self.assertEqual(snapshot["support_draft_request_latency_p50_ms"], 120)
        self.assertEqual(snapshot["support_draft_request_latency_p95_ms"], 500)
        self.assertEqual(snapshot["support_draft_total"], 1)
        self.assertEqual(snapshot["support_human_review_total"], 1)


if __name__ == "__main__":
    unittest.main()