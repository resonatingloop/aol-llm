CREATE TABLE buddy_memories (
    buddy_id TEXT PRIMARY KEY REFERENCES buddies(id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    suppress_injection INTEGER NOT NULL DEFAULT 0,
    watermark_created_at TEXT,
    watermark_message_id TEXT,
    updated_at TEXT NOT NULL,
    CHECK (
        (watermark_created_at IS NULL AND watermark_message_id IS NULL)
        OR (watermark_created_at IS NOT NULL AND watermark_message_id IS NOT NULL)
    )
);

-- Cache token classes are nullable: NULL means the provider did not report the
-- class, while 0 means the provider reported zero tokens for that class.
ALTER TABLE messages ADD COLUMN cache_creation_5m_input_tokens INTEGER;
ALTER TABLE messages ADD COLUMN cache_creation_1h_input_tokens INTEGER;
ALTER TABLE messages ADD COLUMN cache_read_input_tokens INTEGER;
