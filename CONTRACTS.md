# AOL-LLM Contracts

This file defines the engineering contracts for AOL-LLM. `PROJECT_BRIEF.md`
defines what the app is and why it exists; this file defines the stable
interfaces, storage shape, provider boundaries, and implementation rules that
should not drift casually during the build.

## decisions

- buddies are persistent TUI identities; a buddy owns the current provider, model,
  and away-message prompt version.
- away messages are reusable prompts. prompt versions are immutable snapshots.
- conversations store the current/default prompt version, while assistant
  messages store the exact prompt version used for generation.
- `conversations.system_prompt` is legacy transitional storage. new runtime code
  prefers prompt versions and falls back to `system_prompt` only for unmigrated
  or corrupt rows.
- ids are uuid4 hex strings.
- timestamps are stored as ISO 8601 text in sqlite.
- XDG dirs for config and db (`~/.config/aol-llm/`, `~/.local/share/aol-llm/`) via the `platformdirs` lib.
- async everywhere; the provider adapters should not mix sync and async clients.
- no ORM; use plain stdlib `sqlite3` with thin repository functions.
- no retry logic at the provider layer; errors surface to UI, which offers retry.
- cost tracking is baked in via a vendored LiteLLM-derived pricing snapshot
  looked up at send time.
- ask before adding dependencies beyond the ones already listed in `pyproject.toml`.

---

## canonical data types

```python
# core/types.py
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Literal, Protocol

Role = Literal["user", "assistant"]
ProviderKind = Literal["anthropic", "openai_compatible"]
PromptStatus = Literal["draft", "canonical", "archived"]

@dataclass(frozen=True)
class Message:
    id: str                          # uuid4 hex
    conversation_id: str
    role: Role
    content: str
    created_at: datetime
    model: str | None = None         # populated for assistant messages
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    prompt_version_id: str | None = None  # populated for generated assistant messages
    cache_creation_5m_input_tokens: int | None = None
    cache_creation_1h_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None

@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    system_prompt: str | None        # LEGACY fallback during prompt migration
    provider_id: str
    model: str
    created_at: datetime
    updated_at: datetime
    buddy_id: str | None = None
    prompt_version_id: str | None = None
    assistant_name: str | None = None
    archived: bool = False

@dataclass(frozen=True)
class Buddy:
    id: str
    name: str
    screen_name: str
    provider_id: str
    model: str
    prompt_id: str | None
    prompt_version_id: str | None
    created_at: datetime
    updated_at: datetime
    archived: bool = False

@dataclass(frozen=True)
class BuddyMemory:
    buddy_id: str
    memory_text: str
    enabled: bool
    suppress_injection: bool
    watermark_created_at: str | None
    watermark_message_id: str | None
    updated_at: datetime

@dataclass(frozen=True)
class Prompt:
    id: str
    name: str
    gloss: str
    core: str
    signature: str | None
    default_provider: str | None
    default_model: str | None
    status: PromptStatus
    doorwords: str | None
    horizon_minutes: int | None
    mischief_range: str | None
    dismissal_protocol: str | None
    ritual_twin_id: str | None
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class PromptVersion:
    id: str
    prompt_id: str
    parent_version_id: str | None
    name: str
    gloss: str
    core: str
    signature: str | None
    default_provider: str | None
    default_model: str | None
    status: PromptStatus
    doorwords: str | None
    horizon_minutes: int | None
    mischief_range: str | None
    dismissal_protocol: str | None
    ritual_twin_id: str | None
    note: str | None
    created_at: datetime

@dataclass(frozen=True)
class ProviderConfig:
    id: str                          # stable slug, e.g. "anthropic", "openai", "ollama-local"
    kind: ProviderKind
    display_name: str
    base_url: str | None             # required for openai_compatible, ignored for anthropic
    keyring_service: str | None      # None means no auth (e.g. local ollama)
    default_model: str
    available_models: list[str]

@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    model: str
    cache_creation_5m_input_tokens: int | None = None
    cache_creation_1h_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None

@dataclass(frozen=True)
class StreamChunk:
    text: str                        # incremental text; may be ""
    done: bool                       # True only on final chunk
    usage: TokenUsage | None = None  # populated iff done=True
```

## provider interface

```python
# providers/base.py
class Provider(Protocol):
    config: ProviderConfig

    async def stream(
        self,
        messages: list[Message],     # role=user|assistant, ordered
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        ...
```

contract guarantees a Provider must satisfy:
- yields at least one chunk
- the FINAL chunk has `done=True` and a non-None `usage`
- non-final chunks have `done=False` and `usage=None`
- on error, raises a subclass of `ProviderError` (no silent failure, no None returns)
- never mutates the input `messages` list
- never returns provider-native types (no `anthropic.MessageStream` leaking upward)
- keeps provider-specific controls out of the shared interface. Anthropic cache
  marker emission is Anthropic-adapter-internal.

## error taxonomy

```python
# core/errors.py
class ProviderError(Exception):
    """Base for all provider-originating errors."""

class AuthError(ProviderError): ...           # missing/invalid api key
class RateLimitError(ProviderError): ...      # 429
class ContextLengthError(ProviderError): ...  # context window exceeded
class ContentFilterError(ProviderError): ...  # provider refused on policy grounds
class NetworkError(ProviderError): ...        # connection/timeout
class UnknownProviderError(ProviderError): ...  # everything else; preserve original
```

UI maps these to user-readable messages and decides whether to offer retry. providers MUST translate sdk-native exceptions into this taxonomy at their boundary.

## sqlite schema

```sql
-- current schema after migrations
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    system_prompt   TEXT,
    provider_id     TEXT NOT NULL,
    model           TEXT NOT NULL,
    buddy_id        TEXT,
    prompt_version_id TEXT,
    assistant_name  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,
    model           TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        REAL,
    prompt_version_id TEXT,
    cache_creation_5m_input_tokens INTEGER,
    cache_creation_1h_input_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_messages_conv_created ON messages(conversation_id, created_at);

CREATE TABLE providers (
    id                    TEXT PRIMARY KEY,
    kind                  TEXT NOT NULL CHECK (kind IN ('anthropic','openai_compatible')),
    display_name          TEXT NOT NULL,
    base_url              TEXT,
    keyring_service       TEXT,
    default_model         TEXT NOT NULL,
    available_models_json TEXT NOT NULL  -- JSON array
);

CREATE TABLE app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE buddy_memories (
    buddy_id TEXT PRIMARY KEY REFERENCES buddies(id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    suppress_injection INTEGER NOT NULL DEFAULT 0,
    watermark_created_at TEXT,
    watermark_message_id TEXT,
    updated_at TEXT NOT NULL
);

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
    created_at      TEXT NOT NULL
);
```

`002_buddies_prompts.sql` adds:

- `buddies`: one row per Buddy List identity. each buddy stores its current
  provider, model, prompt, and prompt version.
- `prompts`: cross-buddy away-message cards with fields `name`, `gloss`, `core`,
  optional `signature`, optional pinned provider/model, status
  `draft|canonical|archived`, and nullable threshold36 fields (`doorwords`,
  `horizon_minutes`, `mischief_range`, `dismissal_protocol`, `ritual_twin_id`).
- `prompt_versions`: immutable full snapshots of every prompt field plus
  `parent_version_id` and optional `note`.
- `conversations.buddy_id` and `conversations.prompt_version_id`.
- `messages.prompt_version_id` for assistant-message generation provenance.

`004_conversation_assistant_name.sql` adds `conversations.assistant_name` as a
nullable per-chat reply-name override. `NULL` means the transcript and exports
follow the linked buddy's current display name. Message roles remain limited to
`user` and `assistant`; the reply name is presentation metadata only.

The migration seeds a default prompt/version and at least one default buddy so
first run can start a chat without manual setup. Existing conversations are
auto-migrated by deduplicating identical non-empty legacy `system_prompt`
values, creating prompt/version records, linking conversations to the matching
version, and backfilling assistant messages with the conversation prompt
version. User messages leave `prompt_version_id` null.

migrations live in `src/aol_llm/storage/migrations/` as numbered .sql files. db file at `platformdirs.user_data_dir("aol-llm") / "aol-llm.db"`. enable `PRAGMA foreign_keys = ON` on every connection.

current migrations:

- `001_init.sql`
- `002_buddies_prompts.sql`
- `003_anthropic_opus_4_8.sql`
- `004_conversation_assistant_name.sql`
- `005_anthropic_fable_5.sql`
- `006_buddy_memories_and_cache_usage.sql`
- `007_memory_distill_runs.sql`

## storage layer contract

`storage/db.py` exposes module-level functions, not a class. signatures roughly:

- `get_connection() -> sqlite3.Connection`
- `init_db() -> None` (runs pending migrations)
- `create_conversation(title, provider_id, model, system_prompt=None, buddy_id=None, prompt_version_id=None) -> Conversation`
- `list_conversations(include_archived=False) -> list[Conversation]`
- `get_conversation(id) -> Conversation`
- `update_conversation(id, **fields) -> Conversation`
- `delete_conversation(id) -> None`
- `add_message(conversation_id, role, content, **usage_fields) -> Message`
- `list_messages(conversation_id) -> list[Message]`
- `list_buddies(include_archived=False) -> list[Buddy]`
- `get_buddy(id) -> Buddy`
- `get_buddy_memory(buddy_id) -> BuddyMemory | None`
- `upsert_buddy_memory(buddy_id, memory_text, **fields) -> BuddyMemory`
- `set_buddy_memory_enabled(buddy_id, enabled) -> BuddyMemory`
- `set_buddy_memory_suppressed(buddy_id, suppressed) -> BuddyMemory`
- `clear_buddy_memory(buddy_id) -> BuddyMemory`
- `messages_newer_than_watermark_for_buddy(buddy_id) -> list[Message]`
- `commit_buddy_memory_distill(...) -> BuddyMemory`
- `record_memory_distill_run(...) -> MemoryDistillRun`
- `list_memory_distill_runs(buddy_id) -> list[MemoryDistillRun]`
- `buddy_exists(provider_id, model) -> bool` (includes archived buddies)
- `create_prompt(...) -> Prompt`
- `create_prompt_version(...) -> PromptVersion`
- `get_prompt_version(id) -> PromptVersion`

each function gets its own connection (sqlite is cheap). no global cursor, no implicit transactions hanging around.

Startup configured-provider buddy seeding respects archived matching buddies:
if any buddy exists for the provider/model pair, active or archived, startup does
not create a replacement. Explicit user actions such as model switching may
still create an active buddy later through `ensure_buddy`.

prompt resolution order:

1. transient prompt version, once `/sys` exists.
2. `conversation.prompt_version_id`.
3. selected buddy's `prompt_version_id`.
4. legacy `conversation.system_prompt`.

Switching provider/model preserves `conversation.prompt_version_id` when it is
set. The destination buddy's prompt is used only as a fallback for conversations
with no prompt version.

Provider adapters still receive the effective system prompt separately from
ordered user/assistant messages and translate it into each provider's required
API format. Message roles remain limited to `user` and `assistant`.

Prompt assembly lives in `src/aol_llm/prompt_assembly.py`. It produces stable
system blocks in this fixed order:

1. resolved a-way/system prompt, if non-empty.
2. buddy memory block, only when injectable.

Memory is injectable only when a `BuddyMemory` row exists, `enabled` is true,
`memory_text.strip()` is non-empty, and `suppress_injection` is false. Otherwise
the assembly layer injects nothing for memory: no heading, delimiter,
placeholder, or blank section. The flattened system text for
OpenAI-compatible providers is the ordered system blocks joined by blank lines.
Changing the a-way text, memory text, or memory block wrapper changes the cached
prefix.

`ChatService` wires prompt assembly into every streamed provider send. For a
given `ChatService` instance, the buddy memory row is loaded once per
conversation and reused for that conversation so manual memory edits do not
change the prefix mid-conversation. The a-way/system prompt is still resolved on
each send, so editing a conversation's a-way message takes effect immediately
and intentionally changes the cached prefix.

Claude prompt caching is controlled by `app_settings` key
`anthropic_prompt_cache_enabled`. Stored values are `off`, `5m`, or `1h`; legacy
values `0` and `1` read as `off` and `1h`. The Textual slash command
`/cache on|1h|5m|off|status` updates or reads that setting. `/cache on` is an
alias for `/cache 1h`. When enabled for an Anthropic conversation, the
Anthropic adapter sends top-level automatic cache control:

- `5m`: `cache_control: {"type": "ephemeral"}`
- `1h`: `cache_control: {"type": "ephemeral", "ttl": "1h"}`

OpenAI-compatible providers ignore the cache policy.

## memory distiller contract

`src/aol_llm/memory_distiller.py` owns the backend distillation loop. The public
entrypoint is `distill_buddy_memory(buddy_id, mode="incremental", ...)`.
Supported modes are `incremental` and `refactor`; the mode is passed to the
prompt as a runtime input on every batch.

Distillation is per-buddy and oldest-first. Each batch sends the current memory
document plus a transcript slice newer than the buddy watermark to the configured
provider/model. The configured default is `anthropic / claude-opus-4-8`.
Distiller traffic uses the normal provider adapter and pricing layer; there are
no side-channel API calls.

The distiller prompt artifact lives at
`src/aol_llm/data/memory_distiller_prompt.md`. Runtime inputs are delimited as
`<current_memory>`, `<transcript_slice>`, and `<mode>`. The prompt must return a
full rewritten memory document, not a patch or append-only delta.

Before committing a successful provider response, the distiller applies a
deterministic output validation gate. Invalid output is a failed batch: no
`memory_text` replacement and no watermark advance. The validator checks for a
non-empty markdown document, no fenced wrapper or preamble, canonical heading
order, preserved descriptor lines/comments from the current document, and
thread warmth tags only on thread list items.

No-op distillation is required when no messages are newer than the watermark.
That path makes zero provider calls and records a `noop` distill run.

## config & secrets

config at `platformdirs.user_config_dir("aol-llm") / "config.toml"`. schema:

<!-- BEGIN AUTOGEN:provider-defaults-toml -->
```toml
[ui]
theme = "default"
default_provider = "anthropic"
assistant_name = "assistant"

[memory]
distiller_provider = "anthropic"
distiller_model = "claude-opus-4-8"

[providers.anthropic]
default_model = "claude-opus-4-8"

[providers.openai]
base_url = "https://api.openai.com/v1"
default_model = "gpt-5"

[providers.mistral]
base_url = "https://api.mistral.ai/v1"
default_model = "mistral-small-2603"

[providers.xai]
base_url = "https://api.x.ai/v1"
default_model = "grok-4.3"
```
<!-- END AUTOGEN:provider-defaults-toml -->

api keys live in keyring under service `aol-llm.<provider_id>`, key `api_key`. accessed via `keyring.get_password("aol-llm.anthropic", "api_key")`. setup screen writes to keyring; never write keys to config.toml or anywhere on disk.

current built-in keyring services:

- `aol-llm.anthropic`
- `aol-llm.openai`
- `aol-llm.mistral`
- `aol-llm.xai`

## pricing

Static pricing data lives at `src/aol_llm/data/model_prices.json`. It is a
vendored, deterministic subset generated from LiteLLM's upstream pricing file:

```text
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
```

`src/aol_llm/core/pricing.py` reads only the vendored snapshot at runtime. Chat
sending must never hit the network to estimate cost.

`scripts/refresh_pricing.py` refreshes the committed snapshot from LiteLLM.
Run it deliberately, review the diff, and commit the changed
`src/aol_llm/data/model_prices.json` file. Do not hand-edit generated rates.

Every built-in provider/default model must appear in the snapshot. Models with
usable LiteLLM rates are marked `priced: true` and store per-million-token
`input_per_mtok` and `output_per_mtok` values. Models missing usable upstream
rates are explicit unpriced entries, for example:

```json
{
  "priced": false,
  "reason": "missing_from_litellm_snapshot",
  "upstream_model": null
}
```

Cost is computed at send time when usage is known. Explicitly unpriced or
unknown models return `None` from cost estimation and persist `cost_usd = NULL`.
Before release, manually verify current model ids and pricing against official
provider pricing pages even when the LiteLLM snapshot has rates.

Anthropic cache usage fields are normalized into `TokenUsage` as
`cache_creation_5m_input_tokens`, `cache_creation_1h_input_tokens`, and
`cache_read_input_tokens`. The storage schema persists the cache token
breakdown on assistant messages. `NULL` means the provider did not report that
token class; `0` means it reported zero. Five-minute cache writes use 1.25x the
base input-token rate, one-hour cache writes use 2x the base input-token rate,
and cache reads use 0.1x the base input-token rate.

Anthropic Claude Opus 4.8 uses the pinned model id `claude-opus-4-8`.
Anthropic requests for Opus 4.8 enable adaptive thinking with
`thinking: {"type": "adaptive"}`. Opus 4.8 and Opus 4.7 requests omit
`temperature`, `top_p`, and `top_k`; non-default sampling parameters are rejected
by those models.

## textual ui scope (looser, on purpose)

screens:
- `MainScreen`: sidebar with Buddy List and selected-buddy Chats, central `ChatTranscript`, bottom `Composer`, top/bottom `StatusBar` (current model, token+cost running totals)
- `SettingsScreen`: current-chat reply-name override
- `ModelPickerModal`: switch model mid-chat
- `BuddyPickerModal`: switch active buddy from slash command
- `ConfirmModal`: generic yes/no for destructive ops

keybindings (use textual's BINDINGS):

<!-- BEGIN AUTOGEN:keybindings-table -->
| Key | Action |
| --- | --- |
| `f1` | Settings |
| `f2` | Rename buddy |
| `f3` | Send message |
| `f4` | New chat |
| `f5` | Archive chat |
| `f6` | Delete chat |
| `f7` | Retry |
| `ctrl+c` | Quit |
<!-- END AUTOGEN:keybindings-table -->

streaming UI: the ChatTranscript subscribes to the provider's `StreamChunk` async iterator and appends `chunk.text` as it arrives. on `done=True`, persists the message via `storage.add_message` with the usage fields.

composer slash commands are local UI commands and are not persisted as messages.
current commands:

<!-- BEGIN AUTOGEN:slash-commands-list -->
- `/cache on`
- `/cache 1h`
- `/cache 5m`
- `/cache off`
- `/cache status`
- `/help`
- `/copy`
- `/export`
- `/away`
- `/memory status`
- `/memory on`
- `/memory off`
- `/memory forget`
- `/memory distill`
- `/memory refactor`
- `/buddy`
- `/chatname`
- `/quit`
- `/settings`
<!-- END AUTOGEN:slash-commands-list -->

## acceptance criteria per step

each step in the build plan gets a "done when..." clause. examples:

step 2 (data models) done when: all dataclasses in `core/types.py` exist, importable, frozen, no behavior on them (pure data); `core/errors.py` defines the full taxonomy; ruff and mypy pass.

step 3 (provider interface) done when: `providers/base.py` defines `Provider` protocol; `providers/anthropic.py` and `providers/openai_compat.py` both implement it; contract tests in `tests/test_provider_contract.py` pass against both impls using `respx` or similar to mock HTTP; mocked tests cover: normal stream completes with usage, AuthError raised on 401, RateLimitError on 429, NetworkError on connection refused.

step 4 (storage) done when: migrations apply cleanly to a fresh db; all storage functions have at least one test against an in-memory sqlite db; foreign key cascade verified.

step 6 (textual shell) done when: app launches, MainScreen renders with a stub Buddy List and Chats pane, composer accepts input, all bindings registered (can be no-ops). no provider integration yet.

step 7 (wire chat) done when: typing a message and pressing f3 sends to the configured provider, streams response into transcript, persists both user and assistant message with token counts and cost, status bar updates running totals.

---

## documentation drift checks

Every implementation slice must either check these manually or ask the user to
check them:

- whether `PROJECT_BRIEF.md` still reflects the desired product direction.
- whether `CONTRACTS.md` decisions are still correct, not only mechanically
  synchronized.
- whether provider model ids and pricing are current against official provider
  docs.
- whether README/manual instructions are sufficient for a new user.
- whether screenshots, terminal recordings, and release checklist items are
  release-ready.
- whether known-drift items in `docs/CODEBASE_SCHEMA.md` should remain as
  notes or become fixes.
- whether naming choices such as `a-way`, buddy labels, and reply-name language
  still feel right.

Automated tests cover only mechanically checkable claims: keybindings, provider
defaults, keyring service names, migration lists, canonical dataclass fields,
schema module coverage, validation command strings, and stale-name denylist
checks.

required validation commands:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict src tests
```

---

## intentionally unspecified

These choices should be made during implementation and iterated from the working app:

- exact widget layouts
- color scheme
- conversation auto-titling strategy
- markdown rendering specifics
- syntax highlighting choice within code blocks
