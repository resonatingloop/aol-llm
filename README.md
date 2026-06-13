# aol-llm

aol-llm is a local-first Linux chat client for talking to multiple LLM providers
from one interface. The first build is a Textual TUI: fast to iterate,
keyboard-friendly, and practical enough to prove the workflow before deciding
whether the final desktop shell stays Textual or moves to PySide6 or Tauri 2.

## Hook

The shape is an AOL-style unified client for LLM chat: one odd little desktop
place for providers, models, chat history, retry, export, and token/cost
inspection. It starts with Anthropic plus OpenAI-compatible APIs and keeps
provider-native details behind adapters.

## Status

This is pre-release software. The current app can launch as a Textual TUI, store
local chat history in SQLite, stream provider responses through normalized
adapters, switch models, retry the last response, and export chats to Markdown
or JSON.

The first public iteration is source-first: clone the repository, install with
`uv`, configure a provider key, and run the TUI. There is no bundled desktop
installer yet.

Current Textual features:

- Local conversation history in SQLite
- Anthropic and OpenAI-compatible provider adapters
- Streaming assistant responses
- Per-conversation a-way messages
- Provider/model switching
- Retry last response
- Archive/delete with confirmation
- Markdown and JSON export
- Token and estimated cost display

## Install

Requirements:

- Linux
- Python 3.12+
- `uv`
- A desktop keyring supported by the Python `keyring` package

Clone and install:

```bash
git clone https://github.com/resonatingloop/aol-llm.git
cd aol-llm
uv sync
uv run aol-llm
```

Run as a module:

```bash
uv run python -m aol_llm
```

## Configuration

Config uses XDG paths:

- Config: `~/.config/aol-llm/config.toml`
- Data and database: `~/.local/share/aol-llm/`
- API keys: system keyring under `aol-llm.<provider_id>` / `api_key`

Minimal config shape:

<!-- BEGIN AUTOGEN:provider-defaults-toml -->
```toml
[ui]
theme = "default"
default_provider = "anthropic"

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

API keys are intentionally not stored in TOML or SQLite.

Set a key through Python `keyring`. For Anthropic:

```bash
uv run python -c 'import keyring; keyring.set_password("aol-llm.anthropic", "api_key", "YOUR_KEY_HERE")'
```

For the default OpenAI-compatible providers, use service `aol-llm.openai`,
`aol-llm.mistral`, or `aol-llm.xai` and username `api_key`.

See [docs/USER_MANUAL.md](./docs/USER_MANUAL.md) for the current walkthrough.

## Keybindings

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

## Development

Install dependencies:

```bash
uv sync
```

Run the app:

```bash
uv run aol-llm
```

Run checks:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict src tests
```

Update generated documentation blocks:

```bash
uv run python scripts/update_generated_docs.py
```

Format files:

```bash
uv run ruff format
```

Refresh the vendored pricing snapshot from LiteLLM:

```bash
uv run python scripts/refresh_pricing.py
```

The app reads `src/aol_llm/data/model_prices.json` at runtime and never uses the
network for cost estimates. Built-in models missing from LiteLLM are kept as
explicit unpriced entries with reason `missing_from_litellm_snapshot`.

Build package artifacts locally:

```bash
uv build
```

Generated `dist/` files are ignored by git.

## Tech Stack Decisions

- Textual first: validates the product loop quickly on Linux before committing
  to a heavier desktop toolkit.
- Provider adapters: Anthropic and OpenAI-compatible APIs map into one internal
  streaming contract; provider-native objects do not cross into UI or storage.
- Local-first storage: SQLite for conversations/messages/settings and keyring
  for API keys.
- Pricing: committed LiteLLM-derived snapshot data in
  `src/aol_llm/data/model_prices.json`, refreshed by
  `scripts/refresh_pricing.py`, keeps chat runtime offline and deterministic.
- a-way messages live on conversations, not as messages.
- Dataclasses and stdlib SQLite instead of pydantic or an ORM.
- Tests are pulled forward and run through pytest, ruff, and strict mypy.

## Project Docs

- [docs/USER_MANUAL.md](./docs/USER_MANUAL.md) is the current user manual for
  installing, configuring, and using the Textual app.
- [docs/RELEASE_CHECKLIST.md](./docs/RELEASE_CHECKLIST.md) tracks the remaining
  public-release checks.
- [docs/DESKTOP_TARGET_DECISION.md](./docs/DESKTOP_TARGET_DECISION.md) records
  the current Textual/PySide6/Tauri desktop decision.
- [PROJECT_BRIEF.md](./PROJECT_BRIEF.md) explains product direction and the
  implementation plan.
- [CONTRACTS.md](./CONTRACTS.md) defines stable data, provider, storage, config,
  and UI contracts.
- [AGENTS.md](./AGENTS.md) defines repository rules for AI coding agents.
