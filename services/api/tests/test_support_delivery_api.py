import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.persistence import (
    PersistenceError,
    SupportDeliveryConflictError,
    SupportDraftNotFoundError,
)
from app.schemas import SupportDeliveryRequest, SupportDeliveryResponse


class SupportDeliveryRouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.repository.record_support_delivery.return_value = SupportDeliveryResponse(
            delivery_id=uuid4(),
            trace_id="trace-1",
            delivery_status="simulated",
            review_status="edited",
            content_sha256="a" * 64,
            simulated_at=datetime.now(timezone.utc),
        )
        self.payload = SupportDeliveryRequest(trace_id="trace-1")

    def call_delivery(self):
        with patch.object(main, "support_repository", self.repository):
            return main.simulate_support_delivery(self.payload)

    def test_request_rejects_caller_supplied_message_content(self):
        with self.assertRaises(ValidationError):
            SupportDeliveryRequest.model_validate(
                {"trace_id": "trace-1", "draft": "Untrusted caller text."}
            )

    def test_route_records_delivery_by_trace_without_accepting_message_text(self):
        response = self.call_delivery()

        self.assertEqual(response.delivery_status, "simulated")
        self.assertEqual(response.review_status, "edited")
        self.repository.record_support_delivery.assert_called_once_with(
            delivery_request=self.payload
        )

    def test_unknown_trace_returns_not_found(self):
        self.repository.record_support_delivery.side_effect = (
            SupportDraftNotFoundError("Support draft was not found.")
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_delivery()

        self.assertEqual(raised.exception.status_code, 404)

    def test_ineligible_or_duplicate_trace_returns_conflict(self):
        self.repository.record_support_delivery.side_effect = (
            SupportDeliveryConflictError("Draft is not eligible for delivery.")
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_delivery()

        self.assertEqual(raised.exception.status_code, 409)

    def test_persistence_failure_returns_service_unavailable(self):
        self.repository.record_support_delivery.side_effect = PersistenceError(
            "Database unavailable."
        )

        with self.assertRaises(HTTPException) as raised:
            self.call_delivery()

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
