# AOL-LLM Contracts

This file defines the engineering contracts for AOL-LLM. `PROJECT_BRIEF.md`
defines what the app is and why it exists; this file defines the stable
interfaces, storage shape, provider boundaries, and implementation rules that
should not drift casually during the build.

## decisions

- system prompt lives on the Conversation, not as a Message.
- ids are uuid4 hex strings.
- timestamps are stored as ISO 8601 text in sqlite.
- XDG dirs for config and db (`~/.config/aol-llm/`, `~/.local/share/aol-llm/`) via the `platformdirs` lib.
- async everywhere; the provider adapters should not mix sync and async clients.
- no ORM; use plain stdlib `sqlite3` with thin repository functions.
- no retry logic at the provider layer; errors surface to UI, which offers retry.
- cost tracking is baked in via a small static `pricing.json` rate card looked up at send time.
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

@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    system_prompt: str | None        # CANONICAL location for system; never put system in Message
    provider_id: str
    model: str
    created_at: datetime
    updated_at: datetime
    archived: bool = False

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
-- migrations/001_init.sql
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    system_prompt   TEXT,
    provider_id     TEXT NOT NULL,
    model           TEXT NOT NULL,
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
```

migrations live in `src/aol_llm/storage/migrations/` as numbered .sql files. db file at `platformdirs.user_data_dir("aol-llm") / "aol-llm.db"`. enable `PRAGMA foreign_keys = ON` on every connection.

## storage layer contract

`storage/db.py` exposes module-level functions, not a class. signatures roughly:

- `get_connection() -> sqlite3.Connection`
- `init_db() -> None` (runs pending migrations)
- `create_conversation(title, provider_id, model, system_prompt=None) -> Conversation`
- `list_conversations(include_archived=False) -> list[Conversation]`
- `get_conversation(id) -> Conversation`
- `update_conversation(id, **fields) -> Conversation`
- `delete_conversation(id) -> None`
- `add_message(conversation_id, role, content, **usage_fields) -> Message`
- `list_messages(conversation_id) -> list[Message]`

each function gets its own connection (sqlite is cheap). no global cursor, no implicit transactions hanging around.

## config & secrets

config at `platformdirs.user_config_dir("aol-llm") / "config.toml"`. schema:

```toml
[ui]
theme = "default"
default_provider = "anthropic"

[providers.anthropic]
default_model = "claude-opus-4-7"

[providers.openai]
base_url = "https://api.openai.com/v1"
default_model = "gpt-5"
```

api keys live in keyring under service `aol-llm.<provider_id>`, key `api_key`. accessed via `keyring.get_password("aol-llm.anthropic", "api_key")`. setup screen writes to keyring; never write keys to config.toml or anywhere on disk.

## pricing

static rate card at `src/aol_llm/pricing.json`:

```json
{
  "claude-opus-4-7":  {"input_per_mtok": 15.0, "output_per_mtok": 75.0},
  "claude-sonnet-4-6": {"input_per_mtok": 3.0,  "output_per_mtok": 15.0},
  "gpt-5":             {"input_per_mtok": 5.0,  "output_per_mtok": 15.0}
}
```

cost computed at send time when usage is known. unknown models log a warning and set `cost_usd = NULL`. rates above are placeholders. before implementing live pricing defaults, verify current rates against provider pricing pages or leave placeholder rates clearly marked.

## textual ui scope (looser, on purpose)

screens:
- `MainScreen`: sidebar `ConversationList`, central `ChatTranscript`, bottom `Composer`, top/bottom `StatusBar` (current model, token+cost running totals)
- `SettingsScreen`: provider config CRUD, api key entry (writes to keyring)
- `ModelPickerModal`: switch model mid-chat
- `ConfirmModal`: generic yes/no for destructive ops

keybindings (use textual's BINDINGS):
- `ctrl+n` new conversation
- `ctrl+enter` send (enter = newline in composer)
- `ctrl+m` model picker
- `ctrl+,` settings
- `ctrl+r` retry last
- `ctrl+e` export current chat
- `ctrl+d` delete current chat (with ConfirmModal)
- `ctrl+q` quit

streaming UI: the ChatTranscript subscribes to the provider's `StreamChunk` async iterator and appends `chunk.text` as it arrives. on `done=True`, persists the message via `storage.add_message` with the usage fields.

## acceptance criteria per step

each step in the build plan gets a "done when..." clause. examples:

step 2 (data models) done when: all dataclasses in `core/types.py` exist, importable, frozen, no behavior on them (pure data); `core/errors.py` defines the full taxonomy; ruff and mypy pass.

step 3 (provider interface) done when: `providers/base.py` defines `Provider` protocol; `providers/anthropic.py` and `providers/openai_compat.py` both implement it; contract tests in `tests/test_provider_contract.py` pass against both impls using `respx` or similar to mock HTTP; mocked tests cover: normal stream completes with usage, AuthError raised on 401, RateLimitError on 429, NetworkError on connection refused.

step 4 (storage) done when: migrations apply cleanly to a fresh db; all storage functions have at least one test against an in-memory sqlite db; foreign key cascade verified.

step 6 (textual shell) done when: app launches, MainScreen renders with a stub conversation list, composer accepts input, all bindings registered (can be no-ops). no provider integration yet.

step 7 (wire chat) done when: typing a message and pressing ctrl+enter sends to the configured provider, streams response into transcript, persists both user and assistant message with token counts and cost, status bar updates running totals.

---

## intentionally unspecified

These choices should be made during implementation and iterated from the working app:

- exact widget layouts
- color scheme
- conversation auto-titling strategy
- markdown rendering specifics
- syntax highlighting choice within code blocks
