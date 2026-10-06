import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from app.embedder import EmbeddingModelInfo, VECTOR_DIMENSION
from app.persistence import PersistenceError
from app.schemas import SourceDocumentMetadata

IngestionStatus = Literal["created", "reindexed", "unchanged"]


class IngestionVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexedChunk:
    chunk_index: int
    section_path: str
    text: str
    token_estimate: int
    checksum_sha256: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class StoredSourceVersion:
    document_id: UUID
    source_key: str
    title: str
    doc_type: str
    product_area: str
    policy_version: str
    effective_date: date
    access_scope: str
    checksum_sha256: str
    embedding_model: str
    embedding_model_digest: str
    embedding_dimension: int
    chunker_version: str
    chunk_target_tokens: int | None
    chunk_overlap_tokens: int | None
    chunk_count: int


@dataclass(frozen=True)
class IngestionStoreResult:
    document_id: UUID
    status: IngestionStatus
    chunk_count: int


class IngestionRepository(Protocol):
    def get_source_version(
        self,
        *,
        source_key: str,
        policy_version: str,
    ) -> StoredSourceVersion | None:
        ...

    def persist_indexed_version(
        self,
        *,
        metadata: SourceDocumentMetadata,
        raw_content: str,
        checksum_sha256: str,
        embedding_model_info: EmbeddingModelInfo,
        chunker_version: str,
        chunk_target_tokens: int,
        chunk_overlap_tokens: int,
        chunks: tuple[IndexedChunk, ...],
    ) -> IngestionStoreResult:
        ...


def assert_source_version_unchanged(
    existing: StoredSourceVersion,
    *,
    metadata: SourceDocumentMetadata,
    checksum_sha256: str,
) -> None:
    unchanged = {
        "source_key": existing.source_key == metadata.source_key,
        "title": existing.title == metadata.title,
        "doc_type": existing.doc_type == metadata.doc_type,
        "product_area": existing.product_area == metadata.product_area,
        "policy_version": existing.policy_version == metadata.policy_version,
        "effective_date": existing.effective_date == metadata.effective_date,
        "access_scope": existing.access_scope == metadata.access_scope,
        "content": existing.checksum_sha256 == checksum_sha256,
    }
    changed_fields = [field for field, is_unchanged in unchanged.items() if not is_unchanged]
    if changed_fields:
        changed = ", ".join(changed_fields)
        raise IngestionVersionConflict(
            f"Source '{metadata.source_key}' version '{metadata.policy_version}' is immutable; "
            f"changed fields: {changed}. Submit a new policy_version."
        )


def index_configuration_matches(
    existing: StoredSourceVersion,
    *,
    embedding_model_info: EmbeddingModelInfo,
    chunker_version: str,
    chunk_target_tokens: int,
    chunk_overlap_tokens: int,
    chunk_count: int,
) -> bool:
    return (
        existing.embedding_model == embedding_model_info.model_name
        and existing.embedding_model_digest == embedding_model_info.model_digest
        and existing.embedding_dimension == embedding_model_info.dimension
        and existing.chunker_version == chunker_version
        and existing.chunk_target_tokens == chunk_target_tokens
        and existing.chunk_overlap_tokens == chunk_overlap_tokens
        and existing.chunk_count == chunk_count
    )


class PostgresIngestionRepository:
    def __init__(self, *, dsn: str, connect_timeout_seconds: float = 5.0) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout_seconds)

    def get_source_version(
        self,
        *,
        source_key: str,
        policy_version: str,
    ) -> StoredSourceVersion | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    return self._select_source_version(
                        cur,
                        source_key=source_key,
                        policy_version=policy_version,
                    )
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to read indexed source version: {exc}") from exc

    def persist_indexed_version(
        self,
        *,
        metadata: SourceDocumentMetadata,
        raw_content: str,
        checksum_sha256: str,
        embedding_model_info: EmbeddingModelInfo,
        chunker_version: str,
        chunk_target_tokens: int,
        chunk_overlap_tokens: int,
        chunks: tuple[IndexedChunk, ...],
    ) -> IngestionStoreResult:
        self._validate_vectors(embedding_model_info, chunks)
        document_id = uuid5(
            NAMESPACE_URL,
            f"customer-support-copilot:{metadata.source_key}\0{metadata.policy_version}",
        )

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO source_documents (
                            id,
                            source_key,
                            title,
                            doc_type,
                            product_area,
                            policy_version,
                            effective_date,
                            access_scope,
                            raw_content,
                            checksum_sha256,
                            embedding_model,
                            embedding_model_digest,
                            embedding_dimension,
                            chunker_version,
                            chunk_target_tokens,
                            chunk_overlap_tokens
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (source_key, policy_version) DO NOTHING
                        RETURNING id
                        """,
                        (
                            document_id,
                            metadata.source_key,
                            metadata.title,
                            metadata.doc_type,
                            metadata.product_area,
                            metadata.policy_version,
                            metadata.effective_date,
                            metadata.access_scope,
                            raw_content,
                            checksum_sha256,
                            embedding_model_info.model_name,
                            embedding_model_info.model_digest,
                            embedding_model_info.dimension,
                            chunker_version,
                            chunk_target_tokens,
                            chunk_overlap_tokens,
                        ),
                    )
                    inserted = cur.fetchone()

                    if inserted is not None:
                        document_id = inserted[0]
                        status: IngestionStatus = "created"
                    else:
                        existing = self._select_source_version(
                            cur,
                            source_key=metadata.source_key,
                            policy_version=metadata.policy_version,
                            for_update=True,
                        )
                        if existing is None:
                            raise PersistenceError(
                                "Source version conflicted during ingestion but could not be read."
                            )
                        assert_source_version_unchanged(
                            existing,
                            metadata=metadata,
                            checksum_sha256=checksum_sha256,
                        )
                        if index_configuration_matches(
                            existing,
                            embedding_model_info=embedding_model_info,
                            chunker_version=chunker_version,
                            chunk_target_tokens=chunk_target_tokens,
                            chunk_overlap_tokens=chunk_overlap_tokens,
                            chunk_count=len(chunks),
                        ):
                            return IngestionStoreResult(
                                document_id=existing.document_id,
                                status="unchanged",
                                chunk_count=existing.chunk_count,
                            )

                        document_id = existing.document_id
                        status = "reindexed"
                        cur.execute(
                            """
                            UPDATE source_documents
                            SET embedding_model = %s,
                                embedding_model_digest = %s,
                                embedding_dimension = %s,
                                chunker_version = %s,
                                chunk_target_tokens = %s,
                                chunk_overlap_tokens = %s
                            WHERE id = %s
                            """,
                            (
                                embedding_model_info.model_name,
                                embedding_model_info.model_digest,
                                embedding_model_info.dimension,
                                chunker_version,
                                chunk_target_tokens,
                                chunk_overlap_tokens,
                                document_id,
                            ),
                        )
                        cur.execute(
                            "DELETE FROM document_chunks WHERE document_id = %s",
                            (document_id,),
                        )

                    for chunk in chunks:
                        chunk_id = uuid5(
                            document_id,
                            f"{chunk.chunk_index}\0{chunk.section_path}\0{chunk.checksum_sha256}",
                        )
                        embedding_value = json.dumps(
                            chunk.embedding,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        cur.execute(
                            """
                            INSERT INTO document_chunks (
                                id,
                                document_id,
                                chunk_index,
                                section_path,
                                chunk_text,
                                token_estimate,
                                chunk_checksum_sha256,
                                embedding
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                            """,
                            (
                                chunk_id,
                                document_id,
                                chunk.chunk_index,
                                chunk.section_path,
                                chunk.text,
                                chunk.token_estimate,
                                chunk.checksum_sha256,
                                embedding_value,
                            ),
                        )
            return IngestionStoreResult(
                document_id=document_id,
                status=status,
                chunk_count=len(chunks),
            )
        except psycopg.Error as exc:
            raise PersistenceError(f"Failed to persist indexed source version: {exc}") from exc

    @staticmethod
    def _validate_vectors(
        embedding_model_info: EmbeddingModelInfo,
        chunks: tuple[IndexedChunk, ...],
    ) -> None:
        if embedding_model_info.dimension != VECTOR_DIMENSION:
            raise ValueError(
                f"Configured embedding dimension {embedding_model_info.dimension} does not "
                f"match pgvector dimension {VECTOR_DIMENSION}."
            )
        if not chunks:
            raise ValueError("At least one chunk is required to index a source version.")
        for chunk in chunks:
            if len(chunk.embedding) != VECTOR_DIMENSION:
                raise ValueError(
                    f"Chunk {chunk.chunk_index} has {len(chunk.embedding)} embedding values; "
                    f"expected {VECTOR_DIMENSION}."
                )
            if any(not math.isfinite(value) for value in chunk.embedding):
                raise ValueError(
                    f"Chunk {chunk.chunk_index} contains a non-finite embedding value."
                )

    @staticmethod
    def _select_source_version(
        cur: psycopg.Cursor,
        *,
        source_key: str,
        policy_version: str,
        for_update: bool = False,
    ) -> StoredSourceVersion | None:
        query = """
            SELECT
                d.id,
                d.source_key,
                d.title,
                d.doc_type,
                d.product_area,
                d.policy_version,
                d.effective_date,
                d.access_scope,
                d.checksum_sha256,
                d.embedding_model,
                d.embedding_model_digest,
                d.embedding_dimension,
                d.chunker_version,
                d.chunk_target_tokens,
                d.chunk_overlap_tokens,
                (
                    SELECT COUNT(*)
                    FROM document_chunks c
                    WHERE c.document_id = d.id
                )
            FROM source_documents d
            WHERE d.source_key = %s AND d.policy_version = %s
        """
        if for_update:
            query += " FOR UPDATE"
        cur.execute(query, (source_key, policy_version))
        row = cur.fetchone()
        if row is None:
            return None
        return StoredSourceVersion(
            document_id=row[0],
            source_key=row[1],
            title=row[2],
            doc_type=row[3],
            product_area=row[4],
            policy_version=row[5],
            effective_date=row[6],
            access_scope=row[7],
            checksum_sha256=row[8],
            embedding_model=row[9],
            embedding_model_digest=row[10],
            embedding_dimension=row[11],
            chunker_version=row[12],
            chunk_target_tokens=row[13],
            chunk_overlap_tokens=row[14],
            chunk_count=row[15],
        )
