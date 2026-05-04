-- pgvector schema for Aegis RAG service (Phase 3)
-- ADR-008: 768-dim canonical for RESTRICTED/CONFIDENTIAL data
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks_768 (
    id              BIGSERIAL PRIMARY KEY,
    document_id     TEXT        NOT NULL,
    chunk_index     INT         NOT NULL,
    content         TEXT        NOT NULL,
    embedding       vector(768) NOT NULL,
    data_class      TEXT        NOT NULL DEFAULT 'INTERNAL',
    namespace       TEXT        NOT NULL DEFAULT 'default',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- IVFFlat index for approximate nearest-neighbour search
-- lists=100 is a good default for up to ~1M vectors (sqrt(N) rule)
CREATE INDEX IF NOT EXISTS document_chunks_768_embedding_idx
    ON document_chunks_768
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS document_chunks_768_namespace_idx
    ON document_chunks_768 (namespace);

CREATE INDEX IF NOT EXISTS document_chunks_768_data_class_idx
    ON document_chunks_768 (data_class);
