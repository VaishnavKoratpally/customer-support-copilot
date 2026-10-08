import json
import unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from app.embedder import EmbeddingModelInfo, VECTOR_DIMENSION
from app.retrieval_repository import (
    PostgresRetrievalRepository,
    RetrievalIndexConfigurationError,
)


class FakeCursor:
    def __init__(self, result_sets: list[list[tuple]]) -> None:
        self._result_sets = iter(result_sets)
        self._current_rows: list[tuple] = []
        self.executed_queries: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query: str, parameters: tuple | None = None) -> None:
        self.executed_queries.append((query, parameters))
        if query.startswith("SET TRANSACTION"):
            self._current_rows = []
        else:
            self._current_rows = next(self._result_sets)

    def fetchall(self) -> list[tuple]:
        return self._current_rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


class PostgresRetrievalRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = PostgresRetrievalRepository(
            dsn="postgresql://test",
            connect_timeout_seconds=2,
        )
        self.model_info = EmbeddingModelInfo(
            model_name="qwen3-embedding:0.6b",
            model_digest="sha256:test-digest",
            dimension=VECTOR_DIMENSION,
        )
        self.query_vector = (0.125,) * VECTOR_DIMENSION

    def current_document_row(
        self,
        *,
        access_scope: str = "internal",
        model_name: str = "qwen3-embedding:0.6b",
        model_digest: str = "sha256:test-digest",
        version_count: int = 1,
    ) -> tuple:
        return (
            "account-recovery-01",
            "v1",
            access_scope,
            model_name,
            model_digest,
            VECTOR_DIMENSION,
            version_count,
        )

    def make_connection(self, result_sets: list[list[tuple]]) -> tuple[FakeConnection, FakeCursor]:
        cursor = FakeCursor(result_sets)
        return FakeConnection(cursor), cursor

    def test_search_uses_exact_cosine_distance_and_maps_chunk_metadata(self):
        chunk_id = uuid4()
        hit_row = (
            chunk_id,
            "account-recovery-01",
            "Account recovery policy",
            "v1",
            date(2026, 10, 6),
            "internal",
            0,
            "Account recovery",
            "Use password recovery from the sign-in page.",
            0.18,
        )
        connection, cursor = self.make_connection(
            [[self.current_document_row()], [hit_row]]
        )

        with patch(
            "app.retrieval_repository.psycopg.connect",
            return_value=connection,
        ) as connect:
            result = self.repository.search(
                query_vector=self.query_vector,
                embedding_model_info=self.model_info,
                top_k=3,
            )

        connect.assert_called_once_with("postgresql://test", connect_timeout=2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chunk_id, chunk_id)
        self.assertEqual(result[0].source_id, "account-recovery-01")
        self.assertEqual(result[0].policy_version, "v1")
        self.assertEqual(result[0].cosine_distance, 0.18)

        search_sql, search_parameters = cursor.executed_queries[-1]
        self.assertIn("c.embedding <=> %s::vector", search_sql)
        self.assertIn("MAX(effective_date)", search_sql)
        self.assertIn("effective_date <= CURRENT_DATE", search_sql)
        self.assertIn("d.access_scope = ANY(%s::text[])", search_sql)
        self.assertIn("ORDER BY cosine_distance ASC", search_sql)
        self.assertEqual(json.loads(search_parameters[0]), list(self.query_vector))
        self.assertEqual(search_parameters[1], ["public", "internal"])
        self.assertEqual(search_parameters[-1], 3)

    def test_search_rejects_a_stored_model_digest_mismatch(self):
        connection, cursor = self.make_connection(
            [[self.current_document_row(model_digest="sha256:old-digest")]]
        )

        with patch(
            "app.retrieval_repository.psycopg.connect",
            return_value=connection,
        ):
            with self.assertRaisesRegex(
                RetrievalIndexConfigurationError,
                "Re-index the in-scope documents",
            ):
                self.repository.search(
                    query_vector=self.query_vector,
                    embedding_model_info=self.model_info,
                    top_k=3,
                )

        self.assertEqual(len(cursor.executed_queries), 2)

    def test_search_rejects_ambiguous_latest_effective_versions(self):
        connection, cursor = self.make_connection(
            [[self.current_document_row(version_count=2)]]
        )

        with patch(
            "app.retrieval_repository.psycopg.connect",
            return_value=connection,
        ):
            with self.assertRaisesRegex(
                RetrievalIndexConfigurationError,
                "version ambiguity",
            ):
                self.repository.search(
                    query_vector=self.query_vector,
                    embedding_model_info=self.model_info,
                    top_k=3,
                )

        self.assertEqual(len(cursor.executed_queries), 2)

    def test_search_returns_no_hits_when_no_current_documents_are_in_scope(self):
        connection, _ = self.make_connection([[], []])

        with patch(
            "app.retrieval_repository.psycopg.connect",
            return_value=connection,
        ):
            result = self.repository.search(
                query_vector=self.query_vector,
                embedding_model_info=self.model_info,
                top_k=3,
            )

        self.assertEqual(result, ())


if __name__ == "__main__":
    unittest.main()
