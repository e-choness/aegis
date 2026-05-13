-- Aegis AI Gateway — TimescaleDB schema
-- Run once on a fresh TimescaleDB instance.
-- docker exec -i aegis-timescaledb psql -U aegis aegis < scripts/init_db.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS inference_audit_log (
    id              BIGSERIAL,
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    trace_id        VARCHAR(36)     NOT NULL,
    user_id         VARCHAR(255)    NOT NULL,
    team_id         VARCHAR(255)    NOT NULL,
    model_alias     VARCHAR(50)     NOT NULL,
    model_id        VARCHAR(100)    NOT NULL,
    provider        VARCHAR(50)     NOT NULL,
    tier            SMALLINT        NOT NULL,
    data_class      VARCHAR(20)     NOT NULL,
    cost_usd        NUMERIC(10, 6)  NOT NULL,
    input_tokens    INTEGER         NOT NULL DEFAULT 0,
    output_tokens   INTEGER         NOT NULL DEFAULT 0,
    cache_hit       BOOLEAN         NOT NULL DEFAULT FALSE,
    pii_detected    BOOLEAN         NOT NULL DEFAULT FALSE,
    latency_ms      INTEGER         NOT NULL DEFAULT 0,
    PRIMARY KEY (id, timestamp)
);

SELECT create_hypertable('inference_audit_log', 'timestamp', if_not_exists => TRUE);

-- Fast team-level cost queries
CREATE INDEX IF NOT EXISTS idx_audit_team_time
    ON inference_audit_log (team_id, timestamp DESC);

-- Compliance report index: SELECT COUNT(*) WHERE data_class='RESTRICTED' AND tier=1
CREATE INDEX IF NOT EXISTS idx_audit_restricted
    ON inference_audit_log (data_class, tier, timestamp DESC);

-- Compliance invariant view — result must always be 0 rows
CREATE OR REPLACE VIEW restricted_cloud_violations AS
    SELECT * FROM inference_audit_log
    WHERE data_class = 'RESTRICTED' AND tier = 1;

-- Cost per team per month query (TimescaleDB time_bucket)
-- SELECT time_bucket('1 month', timestamp) AS month, team_id, SUM(cost_usd)
-- FROM inference_audit_log GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC;

-- Phase 2 workflow state. The in-process development store mirrors these
-- shapes so production can swap to PostgreSQL without changing API contracts.
CREATE TABLE IF NOT EXISTS workflow_instances (
    id              UUID PRIMARY KEY,
    team_id         VARCHAR(255) NOT NULL,
    user_id         VARCHAR(255) NOT NULL,
    workflow_id     VARCHAR(255) NOT NULL,
    status          VARCHAR(50)  NOT NULL,
    current_step    VARCHAR(255) NOT NULL,
    input_data      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    output_data     JSONB,
    error           TEXT,
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0,
    metadata        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_conversations (
    id                   UUID PRIMARY KEY,
    team_id              VARCHAR(255) NOT NULL,
    user_id              VARCHAR(255) NOT NULL,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE CASCADE,
    workflow_id          VARCHAR(255) NOT NULL,
    state                JSONB        NOT NULL DEFAULT '{}'::jsonb,
    metadata             JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    archived_at          TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS workflow_messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES workflow_conversations(id) ON DELETE CASCADE,
    role            VARCHAR(50) NOT NULL,
    content         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    id                   UUID PRIMARY KEY,
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_name            VARCHAR(255) NOT NULL,
    step_index           INTEGER NOT NULL,
    state                JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
    size_bytes           INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_queue_items (
    id                UUID PRIMARY KEY,
    team_id           VARCHAR(255) NOT NULL,
    user_id           VARCHAR(255) NOT NULL,
    workflow_id       VARCHAR(255) NOT NULL,
    input_data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    priority          INTEGER NOT NULL DEFAULT 5,
    status            VARCHAR(50) NOT NULL DEFAULT 'pending',
    result            JSONB,
    error             TEXT,
    cost_estimate_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflow_instances_team_status
    ON workflow_instances (team_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_conversations_team
    ON workflow_conversations (team_id, workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_workflow_messages_conversation
    ON workflow_messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_instance
    ON workflow_checkpoints (workflow_instance_id, step_index);
CREATE INDEX IF NOT EXISTS idx_workflow_queue_team_status_priority
    ON workflow_queue_items (team_id, status, priority DESC, created_at);
