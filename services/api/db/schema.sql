CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'in_review', 'waiting_on_customer', 'resolved', 'closed')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('customer', 'agent', 'copilot')),
    actor_id TEXT NOT NULL,
    message_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_ticket_created
ON conversation_messages (ticket_id, created_at);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('system', 'agent', 'copilot')),
    actor_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_ticket_created
ON audit_events (ticket_id, created_at);

CREATE TABLE IF NOT EXISTS support_draft_events (
    trace_id TEXT PRIMARY KEY,
    ticket_id TEXT,
    question TEXT NOT NULL,
    intent TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    model_used TEXT NOT NULL,
    draft TEXT NOT NULL,
    citations JSONB NOT NULL,
    retrieval_confidence DOUBLE PRECISION NOT NULL,
    answer_confidence DOUBLE PRECISION NOT NULL,
    requires_human_review BOOLEAN NOT NULL,
    escalation_reason TEXT,
    citation_source_ids JSONB NOT NULL,
    citation_contract_passed BOOLEAN NOT NULL,
    review_triggers JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_support_draft_events_created
ON support_draft_events (created_at);

CREATE TABLE IF NOT EXISTS support_review_events (
    id UUID PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES support_draft_events(trace_id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approve', 'edit', 'reject')),
    ai_draft TEXT NOT NULL,
    edited_draft TEXT,
    final_draft TEXT NOT NULL,
    rejection_reason_code TEXT,
    requires_follow_up BOOLEAN NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    audit_event_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_support_review_events_trace_created
ON support_review_events (trace_id, created_at);

CREATE TABLE IF NOT EXISTS source_documents (
    id UUID PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    product_area TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    effective_date DATE NOT NULL,
    access_scope TEXT NOT NULL CHECK (access_scope IN ('public', 'internal', 'restricted')),
    raw_content TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_estimate INTEGER NOT NULL CHECK (token_estimate > 0),
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document
ON document_chunks (document_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tickets_set_updated_at ON tickets;
CREATE TRIGGER trg_tickets_set_updated_at
BEFORE UPDATE ON tickets
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_source_documents_set_updated_at ON source_documents;
CREATE TRIGGER trg_source_documents_set_updated_at
BEFORE UPDATE ON source_documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();