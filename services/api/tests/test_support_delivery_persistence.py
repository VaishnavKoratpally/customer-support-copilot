import unittest
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import MagicMock, patch

from app.persistence import (
    PostgresSupportRepository,
    SupportDeliveryConflictError,
)
from app.schemas import SupportDeliveryRequest


class SupportDeliveryPersistenceTests(unittest.TestCase):
    def make_repository_context(self, rows):
        cursor = MagicMock()
        cursor.fetchone.side_effect = rows
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor

        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        repository = PostgresSupportRepository(dsn="postgresql://unused")
        return repository, connection, cursor

    def test_not_required_delivery_uses_persisted_enabled_eligibility(self):
        simulated_at = datetime.now(timezone.utc)
        repository, connection, cursor = self.make_repository_context(
            [
                ("Persisted candidate.", "generated", False, "not_required", True, True),
                None,
                (simulated_at,),
            ]
        )

        with patch("app.persistence.psycopg.connect", return_value=connection):
            response = repository.record_support_delivery(
                delivery_request=SupportDeliveryRequest(trace_id="trace-1")
            )

        self.assertTrue(connection.commit.called)
        self.assertEqual(response.review_status, "not_required")
        self.assertEqual(
            response.content_sha256,
            sha256(b"Persisted candidate.").hexdigest(),
        )
        draft_query = cursor.execute.call_args_list[0].args[0]
        self.assertIn("automation_enabled", draft_query)
        self.assertIn("automation_eligibility,eligible_candidate", draft_query)

    def test_not_required_delivery_fails_when_automation_was_disabled(self):
        repository, connection, cursor = self.make_repository_context(
            [
                ("Persisted candidate.", "generated", False, "not_required", False, True),
            ]
        )

        with (
            patch("app.persistence.psycopg.connect", return_value=connection),
            self.assertRaisesRegex(
                SupportDeliveryConflictError,
                "automation is disabled",
            ),
        ):
            repository.record_support_delivery(
                delivery_request=SupportDeliveryRequest(trace_id="trace-2")
            )

        self.assertFalse(connection.commit.called)
        self.assertEqual(cursor.fetchone.call_count, 1)

    def test_human_approved_delivery_does_not_depend_on_automation_eligibility(self):
        simulated_at = datetime.now(timezone.utc)
        repository, connection, _ = self.make_repository_context(
            [
                ("Original draft.", "generated", True, "approved", False, False),
                ("approve", "Human-approved final draft."),
                None,
                (simulated_at,),
            ]
        )

        with patch("app.persistence.psycopg.connect", return_value=connection):
            response = repository.record_support_delivery(
                delivery_request=SupportDeliveryRequest(trace_id="trace-3")
            )

        self.assertTrue(connection.commit.called)
        self.assertEqual(response.review_status, "approved")


if __name__ == "__main__":
    unittest.main()
