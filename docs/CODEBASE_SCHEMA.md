# AOL-LLM Codebase Schema

This document maps the current codebase shape: modules, data flow, contracts,
and known maintenance pressure. `CONTRACTS.md` remains the source of truth for
stable interfaces; this file is a navigational schema for implementation work.

## Top-Level Layout

```text
PROJECT_BRIEF.md          product direction and MVP build plan
CONTRACTS.md              engineering contracts and schema notes
AGENTS.md                 agent workflow and repo policy
README.md                 public setup and project overview
docs/                     user manual, release checklist, decisions, schemas
scripts/                  maintenance scripts
src/aol_llm/              application package
tests/                    pytest coverage for core, storage, providers, service
```

## Runtime Entry Points

```text
src/aol_llm/__init__.py   exposes main()
src/aol_llm/__main__.py   module entrypoint for python -m aol_llm
src/aol_llm/ui/app.py     Textual application class and action coordinator
```

`aol-llm` in `pyproject.toml` points to `aol_llm:main`, which runs the Textual
app defined in `ui/app.py`.

`scripts/baseline_memory_backlog.py` is a guarded, dry-run-first recovery entry
point for owner-approved abandoned memory backlogs. Apply requires a new private
SQLite backup path.

## Core Types And Contracts

```text
src/aol_llm/core/types.py
  Message
  Conversation
  Buddy
  BuddyMemory
  Prompt
  PromptVersion
  ProviderConfig
  ProviderResponseMetadata
  TokenUsage
  StreamChunk

src/aol_llm/core/pricing.py
  ModelPricing
  load_pricing_snapshot
  load_rate_card
  estimate_cost_usd

src/aol_llm/core/requests.py
  NormalizedChatRequest
  normalize_chat_request

src/aol_llm/generation.py
  GenerationResult
  generate

src/aol_llm/prompt_assembly.py
  AssembledPrompt
  assemble_prompt
  should_inject_memory

src/aol_llm/memory_distiller.py
  DistillResult
  InvalidMemoryOutputError
  distill_buddy_memory
  load_distiller_prompt
  validate_memory_output

src/aol_llm/core/errors.py
  ProviderError
  AuthError
  RateLimitError
  ContextLengthError
  ContentFilterError
  NetworkError
  UnknownProviderError

src/aol_llm/providers/base.py
  Provider protocol
```

Provider adapters must yield normalized `StreamChunk` objects and raise
`ProviderError` subclasses at the provider boundary. Anthropic automatic prompt
caching with `5m` or `1h` TTL is configured inside the Anthropic adapter, not
through the shared provider protocol. Cache creation/read token counts and
disjoint OpenAI cache-write tokens are normalized in `TokenUsage` for cost
calculation and persisted on assistant messages when reported.

For Anthropic streams, input and cache usage are read from
`message_start.message.usage`; later cumulative `message_delta.usage` fields are
merged without erasing the start-event cache breakdown. When Anthropic reports
both aggregate cache creation and the per-TTL breakdown, the adapter requires
the aggregate to equal the 5-minute plus 1-hour buckets. When only the aggregate
is present, it is assigned to the request's single configured cache TTL; the
Anthropic default remains 5 minutes when no explicit TTL is configured. These
buckets stay disjoint for cost calculation.

Provider-specific request deadlines also stay on concrete adapters rather than
the shared `Provider.stream(...)` signature. `OpenAICompatibleProvider` accepts
`request_timeout_seconds` for Chat Completions; Responses retains its timeout in
`OpenAIResponseOptions`. Both default to 60 seconds when a consumer does not
override them.

Final stream chunks may also carry normalized provider-reported model,
response ids, termination reasons, and service tiers in
`ProviderResponseMetadata`. The stateless generation facade
collects a stream into text, usage, cost, and requested-versus-reported
provenance without importing Textual or owning storage, prompts, secrets,
retries, or cancellation.

Stored message roles remain `user` and `assistant`. UI-facing reply names are
presentation metadata resolved from the conversation override or buddy name.
Prompt assembly produces stable system blocks in a-way then memory order and
flattens them to plain system text for provider adapters that do not accept
structured system blocks. `ChatService` freezes the buddy memory row per
conversation for its own process lifetime; a-way prompt resolution remains
per-send.

`memory_distiller.py` runs backend buddy-memory distillation. It batches
messages newer than the buddy watermark oldest-first, calls the configured
provider/model through the normal provider adapter, validates the returned full
memory document, then atomically commits memory replacement plus watermark
advance. Invalid output is recorded as a failed distill run and does not update
memory. Anthropic distiller construction disables adaptive thinking while
ordinary Anthropic chat construction keeps it. A latest attempted run with an
`invalid_output:` failure pauses automatic lifecycle retries; manual distillation
is still available and a successful attempt clears the pause.

## Config And Secrets

```text
src/aol_llm/config.py
  XDG path helpers
  TOML load/save
  built-in provider defaults
  built-in memory distiller defaults
  missing built-in provider merge for existing configs

src/aol_llm/secrets.py
  keyring service naming
  get/set/delete API key helpers
```

Built-in providers currently defined by default config:

```text
<!-- BEGIN AUTOGEN:provider-defaults-text -->
anthropic  claude-opus-4-8
openai     gpt-5                     https://api.openai.com/v1
mistral    mistral-small-2603        https://api.mistral.ai/v1
xai        grok-4.3                  https://api.x.ai/v1
<!-- END AUTOGEN:provider-defaults-text -->
```

API keys use service `aol-llm.<provider_id>` and username `api_key`.

Current built-in keyring services:

```text
aol-llm.anthropic
aol-llm.openai
aol-llm.mistral
aol-llm.xai
```

## Pricing Data

```text
src/aol_llm/data/model_prices.json
  committed LiteLLM-derived pricing snapshot

src/aol_llm/data/memory_distiller_prompt.md
  committed distiller prompt artifact

scripts/refresh_pricing.py
  refreshes the vendored pricing snapshot from LiteLLM upstream
```

Runtime chat code reads `src/aol_llm/data/model_prices.json` through
`core/pricing.py`; it never calls the network for cost estimation. The refresh
script downloads:

```text
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
```

Every built-in model from config and `DEFAULT_PROVIDER_MODELS` must have a
snapshot entry. Priced entries include per-million-token rates. Missing upstream
rates are explicit unpriced entries with reason
`missing_from_litellm_snapshot`.

## Storage

```text
src/aol_llm/storage/connection.py
  sqlite connection setup
  sorted SQL migration runner

src/aol_llm/storage/migrations/
  001_init.sql
  002_buddies_prompts.sql
  003_anthropic_opus_4_8.sql
  004_conversation_assistant_name.sql
  005_anthropic_fable_5.sql
  006_buddy_memories_and_cache_usage.sql
  007_memory_distill_runs.sql
  008_openai_gpt_5_6.sql

src/aol_llm/storage/rows.py
  sqlite.Row -> dataclass conversion

src/aol_llm/storage/db.py
  repository functions over sqlite3
  buddy memory read/write helpers
  memory distill commit and run-ledger helpers
  latest attempted-run lookup
  guarded empty-memory backlog preview and baseline transaction
```

Primary tables:

```text
conversations
messages
providers
app_settings
buddies
buddy_memories
memory_distill_runs
prompts
prompt_versions
schema_migrations
```

Repository style is module-level functions, not repository classes. Connections
are opened per operation and foreign keys are enabled in `connection.py`.

## Chat Service Flow

```text
src/aol_llm/chat.py
  ChatService
  ChatEvent
  ModelChoice
  DEFAULT_PROVIDER_MODELS
```

Main responsibilities:

```text
init
  apply migrations
  ensure configured provider/default-model buddies exist
  skip startup buddy seeding when a matching archived buddy exists

send_message
  add user message
  assemble a-way plus frozen buddy memory into system prompt
  stream provider response
  persist assistant message with usage, cost, model, prompt provenance
  pass prompt-cache policy to Anthropic when enabled in app_settings

retry_last_response
  remove trailing assistant message if present
  stream a replacement from the remaining user-ending transcript

switch_model
  move conversation provider/model and attach/create matching buddy
  preserve conversation prompt version, falling back to buddy prompt only if missing

update_system_prompt
  create prompt/version for the current chat a-way

update_conversation_reply_name
  set or clear per-chat reply-name override
```

Prompt resolution order:

```text
conversation.prompt_version_id
buddy.prompt_version_id
conversation.system_prompt legacy fallback
```

Reply-name resolution order:

```text
conversation.assistant_name
buddy.screen_name or buddy.name
"assistant" internal fallback
```

## Provider Adapters

```text
src/aol_llm/providers/registry.py
  ProviderConfig.kind -> provider adapter
  distiller-specific Anthropic construction without adaptive thinking

src/aol_llm/providers/anthropic.py
  Anthropic Messages API
  top-level automatic prompt cache control
  opt-in explicit stable system and rolling-history cache breakpoints
  Opus 4.8 adaptive thinking
  Opus 4.7/4.8 sampling-parameter omission

src/aol_llm/providers/openai_compat.py
  OpenAI-compatible /chat/completions streaming
  opt-in OpenAI Responses API delegation
  OpenAI API special casing:
    developer role for system prompt
    max_completion_tokens
    no temperature
  Generic compatible providers:
    system role
    max_tokens
    temperature included

src/aol_llm/providers/openai_responses.py
  OpenAI /responses streaming for opt-in provider controls
  text verbosity and stable prompt cache key payload fields
  Responses event and token-usage normalization

src/aol_llm/providers/_http.py
  SSE parsing
  HTTP status translation
  bounded error-body excerpts
```

Empty provider modules currently exist:

```text
src/aol_llm/providers/claude.py
src/aol_llm/providers/gpt.py
```

They are not imported by the registry.

## Textual UI

```text
src/aol_llm/ui/app.py
  THRESHOLD36 App
  action handlers
  current buddy/conversation state
  transcript reload and streaming coordination
  slash command dispatch for prompt-cache and chat controls

src/aol_llm/ui/commands.py
  composer slash command parsing

src/aol_llm/ui/screens.py
  MainScreen
  SettingsScreen for current-chat reply-name override

src/aol_llm/ui/modals.py
  ModelPickerModal
  BuddyPickerModal
  RenameModal
  SystemPromptModal
  ExportFormatModal
  ConfirmModal

src/aol_llm/ui/widgets.py
  BuddyList
  ConversationList
  ChatTranscript
  Composer
  StatusBar
  format_usage_status

src/aol_llm/ui/styles.py
  CSS
  key bindings
```

Current keymap:

```text
<!-- BEGIN AUTOGEN:keybindings-text -->
f1       Settings
f2       Rename buddy
f3       Send message
f4       New chat
f5       Archive chat
f6       Delete chat
f7       Retry
ctrl+c   Quit
<!-- END AUTOGEN:keybindings-text -->
escape   cancel modal/settings
```

Binding/action audit status: all bindings have matching app actions or Textual's
built-in `quit`.

## Export

```text
src/aol_llm/export.py
  export_markdown
  export_json
  export_last_pair_markdown
  write_export
```

Markdown export renders user-facing reply names for assistant messages when a
resolved reply name is supplied. Last-pair export copies only the final complete
user/assistant exchange. JSON preserves stored roles and can include `reply_name`
metadata.

## Tests

```text
tests/test_core_contracts.py       dataclasses, pricing, request normalization
tests/test_provider_contract.py    provider protocol behavior
tests/test_provider_adapters.py    Anthropic and OpenAI-compatible adapters
tests/test_config.py               config defaults, merge behavior, XDG paths
tests/test_secrets.py              keyring helper behavior
tests/test_storage_migration.py    SQL migrations
tests/test_storage_db.py           repository behavior
tests/test_memory_distiller.py     backend distillation and validation
tests/test_memory_recovery_script.py  dry-run/apply and backup recovery path
tests/test_chat_service.py         orchestration and management behavior
tests/test_export.py               Markdown/JSON export behavior
tests/test_ui_commands.py          composer slash command parsing
tests/test_docs_contracts.py       docs/schema drift checks, pricing coverage
```

Required validation:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict src tests
```

## Known Drift And Maintenance Pressure

- Global `[ui].assistant_name` still parses and writes through config as legacy
  data, while runtime display now uses buddy/per-chat reply names.
- Large modules above the repo's soft size target: `storage/db.py`, `chat.py`,
  `ui/app.py`, and `ui/modals.py`.
