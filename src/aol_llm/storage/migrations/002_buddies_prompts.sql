CREATE TABLE prompts (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    gloss                 TEXT NOT NULL,
    core                  TEXT NOT NULL,
    signature             TEXT,
    default_provider      TEXT,
    default_model         TEXT,
    status                TEXT NOT NULL CHECK (status IN ('draft','canonical','archived')),
    doorwords             TEXT,
    horizon_minutes       INTEGER,
    mischief_range        TEXT,
    dismissal_protocol    TEXT,
    ritual_twin_id        TEXT,
    current_version_id    TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE prompt_versions (
    id                    TEXT PRIMARY KEY,
    prompt_id             TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    parent_version_id     TEXT REFERENCES prompt_versions(id),
    name                  TEXT NOT NULL,
    gloss                 TEXT NOT NULL,
    core                  TEXT NOT NULL,
    signature             TEXT,
    default_provider      TEXT,
    default_model         TEXT,
    status                TEXT NOT NULL CHECK (status IN ('draft','canonical','archived')),
    doorwords             TEXT,
    horizon_minutes       INTEGER,
    mischief_range        TEXT,
    dismissal_protocol    TEXT,
    ritual_twin_id        TEXT,
    note                  TEXT,
    created_at            TEXT NOT NULL
);

CREATE TABLE buddies (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    screen_name           TEXT NOT NULL,
    provider_id           TEXT NOT NULL,
    model                 TEXT NOT NULL,
    prompt_id             TEXT REFERENCES prompts(id),
    prompt_version_id     TEXT REFERENCES prompt_versions(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_buddies_provider_model ON buddies(provider_id, model);
CREATE INDEX idx_prompt_versions_prompt ON prompt_versions(prompt_id, created_at);

ALTER TABLE conversations ADD COLUMN buddy_id TEXT REFERENCES buddies(id);
ALTER TABLE conversations ADD COLUMN prompt_version_id TEXT REFERENCES prompt_versions(id);
ALTER TABLE messages ADD COLUMN prompt_version_id TEXT REFERENCES prompt_versions(id);

CREATE TEMP TABLE _default_prompt (
    prompt_id TEXT NOT NULL,
    version_id TEXT NOT NULL
);

INSERT INTO _default_prompt (prompt_id, version_id)
VALUES (lower(hex(randomblob(16))), lower(hex(randomblob(16))));

INSERT INTO prompts (
    id,
    name,
    gloss,
    core,
    status,
    current_version_id,
    created_at,
    updated_at
)
SELECT
    prompt_id,
    'Available',
    'ready to chat',
    '',
    'canonical',
    version_id,
    datetime('now'),
    datetime('now')
FROM _default_prompt;

INSERT INTO prompt_versions (
    id,
    prompt_id,
    name,
    gloss,
    core,
    status,
    note,
    created_at
)
SELECT
    version_id,
    prompt_id,
    'Available',
    'ready to chat',
    '',
    'canonical',
    'seeded default away message',
    datetime('now')
FROM _default_prompt;

CREATE TEMP TABLE _legacy_prompts AS
SELECT
    core,
    'Migrated Away Message ' || row_number() OVER (ORDER BY core) AS name,
    lower(hex(randomblob(16))) AS prompt_id,
    lower(hex(randomblob(16))) AS version_id
FROM (
    SELECT DISTINCT trim(system_prompt) AS core
    FROM conversations
    WHERE system_prompt IS NOT NULL
      AND trim(system_prompt) <> ''
);

INSERT INTO prompts (
    id,
    name,
    gloss,
    core,
    status,
    current_version_id,
    created_at,
    updated_at
)
SELECT
    prompt_id,
    name,
    'migrated from chat',
    core,
    'canonical',
    version_id,
    datetime('now'),
    datetime('now')
FROM _legacy_prompts;

INSERT INTO prompt_versions (
    id,
    prompt_id,
    name,
    gloss,
    core,
    status,
    note,
    created_at
)
SELECT
    version_id,
    prompt_id,
    name,
    'migrated from chat',
    core,
    'canonical',
    'migrated from conversation.system_prompt',
    datetime('now')
FROM _legacy_prompts;

UPDATE conversations
SET prompt_version_id = (
    SELECT version_id
    FROM _legacy_prompts
    WHERE _legacy_prompts.core = trim(conversations.system_prompt)
)
WHERE system_prompt IS NOT NULL
  AND trim(system_prompt) <> '';

UPDATE conversations
SET prompt_version_id = (SELECT version_id FROM _default_prompt)
WHERE prompt_version_id IS NULL;

CREATE TEMP TABLE _buddy_seed AS
SELECT
    provider_id,
    model,
    lower(hex(randomblob(16))) AS buddy_id
FROM (
    SELECT DISTINCT provider_id, model
    FROM conversations
    UNION
    SELECT 'anthropic' AS provider_id, 'claude-opus-4-7' AS model
);

INSERT INTO buddies (
    id,
    name,
    screen_name,
    provider_id,
    model,
    prompt_id,
    prompt_version_id,
    created_at,
    updated_at
)
SELECT
    buddy_id,
    provider_id || ' / ' || model,
    provider_id || ' / ' || model,
    provider_id,
    model,
    (SELECT prompt_id FROM _default_prompt),
    (SELECT version_id FROM _default_prompt),
    datetime('now'),
    datetime('now')
FROM _buddy_seed;

UPDATE conversations
SET buddy_id = (
    SELECT buddy_id
    FROM _buddy_seed
    WHERE _buddy_seed.provider_id = conversations.provider_id
      AND _buddy_seed.model = conversations.model
);

UPDATE messages
SET prompt_version_id = (
    SELECT prompt_version_id
    FROM conversations
    WHERE conversations.id = messages.conversation_id
)
WHERE role = 'assistant';

DROP TABLE _buddy_seed;
DROP TABLE _legacy_prompts;
DROP TABLE _default_prompt;
