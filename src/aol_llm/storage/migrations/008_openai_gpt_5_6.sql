WITH gpt_5_6_models(model) AS (
    VALUES
        ('gpt-5.6-sol'),
        ('gpt-5.6-terra'),
        ('gpt-5.6-luna')
),
available_prompt AS (
    SELECT
        prompts.id AS prompt_id,
        prompt_versions.id AS prompt_version_id
    FROM prompt_versions
    JOIN prompts ON prompts.current_version_id = prompt_versions.id
    WHERE prompts.name = 'Available'
    ORDER BY prompts.created_at
    LIMIT 1
)
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
    'openai / ' || gpt_5_6_models.model,
    'openai / ' || gpt_5_6_models.model,
    'openai',
    gpt_5_6_models.model,
    available_prompt.prompt_id,
    available_prompt.prompt_version_id,
    datetime('now'),
    datetime('now'),
    0
FROM gpt_5_6_models
CROSS JOIN available_prompt
WHERE NOT EXISTS (
    SELECT 1
    FROM buddies
    WHERE provider_id = 'openai'
      AND model = gpt_5_6_models.model
);
