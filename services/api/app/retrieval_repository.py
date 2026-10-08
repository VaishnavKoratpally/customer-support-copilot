import json
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

import psycopg

from app.embedder import EmbeddingModelInfo, VECTOR_DIMENSION
from app.persistence import PersistenceError

ALLOWED_ACCESS_SCOPES = ("public", "internal")

_CURRENT_DOCUMENTS_CTE = """
WITH latest_effective_dates AS (
    SELECT source_key, MAX(effective_date) AS effective_date
    FROM source_documents
    WHERE effective_date <= CURRENT_DATE
    GROUP BY source_key
),
current_documents AS (
    SELECT
        d.id,
        d.source_key,
        d.title,
        d.policy_version,
        d.effective_date,
        d.access_scope,
        d.embedding_model,
        d.embedding_model_digest,
        d.embedding_dimension,
        COUNT(*) OVER (PARTITION BY d.source_key) AS current_version_count
    FROM source_documents d
    INNER JOIN latest_effective_dates latest
        ON latest.source_key = d.source_key
        AND latest.effective_date = d.effective_date
)
"""


class RetrievalIndexConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    source_id: str
    title: str
    policy_version: str
    effective_date: date
    access_scope: str
    chunk_index: int
    section_path: str
    text: str
    cosine_distance: float


class RetrievalRepository(Protocol):
    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        embedding_model_info: EmbeddingModelInfo,
        top_k: int,
    ) -> tuple[RetrievedChunk, ...]:
        ...


class PostgresRetrievalRepository:
    def __init__(self, *, dsn: str, connect_timeout_seconds: float = 5.0) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout_seconds)

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        embedding_model_info: EmbeddingModelInfo,
        top_k: int,
    ) -> tuple[RetrievedChunk, ...]:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10.")
        if (
            embedding_model_info.dimension != VECTOR_DIMENSION
            or len(query_vector) != VECTOR_DIMENSION
        ):
            raise RetrievalIndexConfigurationError(
                f"Query vector must have {VECTOR_DIMENSION} dimensions."
            )

        vector_value = json.dumps(query_vector, separators=(",", ":"), allow_nan=False)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cur.execute(
                        _CURRENT_DOCUMENTS_CTE
                        + """
                        SELECT
                            source_key,
                            policy_version,
                            access_scope,
                            embedding_model,
                            embedding_model_digest,
                            embedding_dimension,
                            current_version_count
                        FROM current_documents
                        ORDER BY source_key, policy_version
                        """
                    )
                    current_documents = cur.fetchall()
                    self._validate_current_documents(
                        current_documents,
                        embedding_model_info=embedding_model_info,
                    )

                    cur.execute(
                        _CURRENT_DOCUMENTS_CTE
                        + """
                        SELECT
                            c.id,
                            d.source_key,
                            d.title,
                            d.policy_version,
                            d.effective_date,
                            d.access_scope,
                            c.chunk_index,
                            c.section_path,
                            c.chunk_text,
                            c.embedding <=> %s::vector AS cosine_distance
                        FROM document_chunks c
                        INNER JOIN current_documents d ON d.id = c.document_id
                        WHERE d.access_scope = ANY(%s::text[])
                          AND d.embedding_model = %s
                          AND d.embedding_model_digest = %s
                          AND d.embedding_dimension = %s
                        ORDER BY cosine_distance ASC, d.source_key ASC, c.chunk_index ASC
                        LIMIT %s
                        """,
                        (
                            vector_value,
                            list(ALLOWED_ACCESS_SCOPES),
                            embedding_model_info.model_name,
                            embedding_model_info.model_digest,
                            embedding_model_info.dimension,
                            top_k,
                        ),
                    )
                    rows = cur.fetchall()
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to retrieve indexed support chunks: {exc}") from exc

        return tuple(
            RetrievedChunk(
                chunk_id=row[0],
                source_id=row[1],
                title=row[2],
                policy_version=row[3],
                effective_date=row[4],
                access_scope=row[5],
                chunk_index=row[6],
                section_path=row[7],
                text=row[8],
                cosine_distance=float(row[9]),
            )
            for row in rows
        )

    @staticmethod
    def _validate_current_documents(
        current_documents: list[tuple],
        *,
        embedding_model_info: EmbeddingModelInfo,
    ) -> None:
        in_scope_documents = [
            row for row in current_documents if row[2] in ALLOWED_ACCESS_SCOPES
        ]
        ambiguous_sources = {
            row[0] for row in in_scope_documents if row[6] > 1
        }
        if ambiguous_sources:
            raise RetrievalIndexConfigurationError(
                "An in-scope source has multiple policy versions with the same latest "
                "effective date; resolve the version ambiguity before retrieval."
            )

        has_incompatible_embeddings = any(
            row[3] != embedding_model_info.model_name
            or row[4] != embedding_model_info.model_digest
            or row[5] != embedding_model_info.dimension
            for row in in_scope_documents
        )
        if has_incompatible_embeddings:
            raise RetrievalIndexConfigurationError(
                "In-scope indexed vectors do not match the query embedding model and digest. "
                "Re-index the in-scope documents before retrieval."
            )
