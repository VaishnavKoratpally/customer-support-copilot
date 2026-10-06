BEGIN;

ALTER TABLE source_documents
    DROP CONSTRAINT IF EXISTS source_documents_source_key_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'source_documents_source_key_policy_version_key'
          AND conrelid = 'source_documents'::regclass
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_source_key_policy_version_key
            UNIQUE (source_key, policy_version);
    END IF;
END;
$$;

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS embedding_model TEXT NOT NULL DEFAULT 'untracked',
    ADD COLUMN IF NOT EXISTS embedding_model_digest TEXT NOT NULL DEFAULT 'untracked',
    ADD COLUMN IF NOT EXISTS embedding_dimension SMALLINT NOT NULL DEFAULT 1024,
    ADD COLUMN IF NOT EXISTS chunker_version TEXT NOT NULL DEFAULT 'legacy-unknown',
    ADD COLUMN IF NOT EXISTS chunk_target_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS chunk_overlap_tokens INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'source_documents_embedding_dimension_check'
          AND conrelid = 'source_documents'::regclass
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_embedding_dimension_check
            CHECK (embedding_dimension = 1024);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'source_documents_chunk_target_tokens_check'
          AND conrelid = 'source_documents'::regclass
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_chunk_target_tokens_check
            CHECK (chunk_target_tokens IS NULL OR chunk_target_tokens > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'source_documents_chunk_overlap_tokens_check'
          AND conrelid = 'source_documents'::regclass
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_chunk_overlap_tokens_check
            CHECK (chunk_overlap_tokens IS NULL OR chunk_overlap_tokens >= 0);
    END IF;
END;
$$;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS section_path TEXT NOT NULL DEFAULT 'legacy-unknown',
    ADD COLUMN IF NOT EXISTS chunk_checksum_sha256 TEXT;

DROP INDEX IF EXISTS idx_document_chunks_embedding;

COMMIT;
