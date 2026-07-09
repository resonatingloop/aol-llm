CREATE TABLE memory_distill_runs (
    id              TEXT PRIMARY KEY,
    buddy_id        TEXT NOT NULL REFERENCES buddies(id) ON DELETE CASCADE,
    provider_id     TEXT NOT NULL,
    model           TEXT NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('incremental', 'refactor')),
    status          TEXT NOT NULL CHECK (status IN ('success', 'failed', 'noop')),
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        REAL,
    cache_creation_5m_input_tokens INTEGER,
    cache_creation_1h_input_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    watermark_created_at TEXT,
    watermark_message_id TEXT,
    failure_reason  TEXT,
    created_at      TEXT NOT NULL,
    CHECK (
        (watermark_created_at IS NULL AND watermark_message_id IS NULL)
        OR (watermark_created_at IS NOT NULL AND watermark_message_id IS NOT NULL)
    )
);

CREATE INDEX idx_memory_distill_runs_buddy_created
    ON memory_distill_runs(buddy_id, created_at);
