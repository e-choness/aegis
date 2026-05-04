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
