INSERT INTO buddies (
    id,
    name,
    screen_name,
    provider_id,
    model,
    prompt_id,
    prompt_version_id,
    created_at,
    updated_at,
    archived
)
SELECT
    lower(hex(randomblob(16))),
    'anthropic / claude-opus-4-8',
    'anthropic / claude-opus-4-8',
    'anthropic',
    'claude-opus-4-8',
    prompts.id,
    prompt_versions.id,
    datetime('now'),
    datetime('now'),
    0
FROM prompt_versions
JOIN prompts ON prompts.current_version_id = prompt_versions.id
WHERE prompts.name = 'Available'
  AND NOT EXISTS (
      SELECT 1
      FROM buddies
      WHERE provider_id = 'anthropic'
        AND model = 'claude-opus-4-8'
  )
ORDER BY prompts.created_at
LIMIT 1;
