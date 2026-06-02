# AOL-LLM User Manual

This manual covers the current Textual version of aol-llm. The app is still
pre-release, so a few setup tasks are manual.

## What It Does

aol-llm is a local desktop chat client for LLM providers. It keeps conversations
in a local SQLite database, stores API keys in your system keyring, streams
responses into a terminal UI, and can export chats to Markdown or JSON.

The first supported provider families are:

- Anthropic
- OpenAI-compatible APIs

## Install And Run

From the project directory:

```bash
uv sync
uv run aol-llm
```

You can also run it as a module:

```bash
uv run python -m aol_llm
```

The first public iteration is installed from source. There is no bundled desktop
installer yet.

## First Setup

The app reads provider defaults from:

```text
~/.config/aol-llm/config.toml
```

If the file does not exist, defaults are loaded in memory. A minimal config is:

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

API keys are not stored in this file.

To make OpenAI the default provider, set:

```toml
[ui]
theme = "default"
default_provider = "openai"
```

## API Keys

API keys live in your system keyring. For Anthropic, the app reads:

```text
service:  aol-llm.anthropic
username: api_key
```

Set the Anthropic key with:

```bash
uv run python -c 'import keyring; keyring.set_password("aol-llm.anthropic", "api_key", "YOUR_KEY_HERE")'
```

For OpenAI-compatible providers, replace `anthropic` with the provider id. For
the default OpenAI-compatible config, that is:

```text
service:  aol-llm.openai
username: api_key
```

Set that key with:

```bash
uv run python -c 'import keyring; keyring.set_password("aol-llm.openai", "api_key", "YOUR_KEY_HERE")'
```

## Chat Basics

When the app opens, it creates or loads the most recently updated conversation.
The main screen has:

- A conversation list on the left
- The transcript in the center
- A composer at the bottom
- Provider/model and token/cost totals in the status area

The transcript and conversation list are scrollable when their contents are
longer than the visible area. New chat output scrolls the transcript to the
bottom as it streams.

Type a message in the composer and send it with `f5`. Regular `enter`
continues editing in the composer.

The settings screen can update the reply name used by the current chat.
Provider config and API keys are still edited manually for now.

## Keybindings

| Key | Action |
| --- | --- |
| `f1` | Open settings |
| `f2` | Pick model |
| `f3` | Edit current conversation a-way |
| `f4` | Rename current buddy |
| `f5` | Send message |
| `f6` | New conversation |
| `f7` | Retry last response |
| `f8` | Rename current chat |
| `f9` | Export current chat |
| `ctrl+x` | Archive current chat |
| `ctrl+d` | Delete current chat |
| `ctrl+c` | Quit |
| `escape` | Close settings or cancel a modal |

Destructive actions ask for confirmation first.

`f1` opens settings from the main screen and closes settings when pressed again.

## Reply Name

Use `f1` to open settings and change the reply name for the current chat. Blank
the field to follow the current buddy name.

This is local display text only. Stored messages still use the internal
`assistant` role, and provider requests are unchanged.

## a-way Messages

a-way messages are per-conversation. Use `f3` to edit the current
conversation's a-way. Save a blank a-way to clear it.

a-way messages are stored on the conversation record, not in the message list.
Future sends in that conversation use the saved a-way; existing messages are not
changed.

## Export

Use `f9` to export the current chat. Choose Markdown for a readable document
or JSON for structured data.

When running with the default app database path, exports are written under:

```text
~/.local/share/aol-llm/exports/
```

## Local Files

The app follows XDG paths:

```text
Config: ~/.config/aol-llm/config.toml
Data:   ~/.local/share/aol-llm/
DB:     ~/.local/share/aol-llm/aol-llm.db
```

The database stores conversations, messages, provider rows, settings, token
usage, and estimated cost fields. API keys stay in keyring.

## Troubleshooting

### Missing Anthropic API Key

The app is looking for:

```text
service:  aol-llm.anthropic
username: api_key
```

Check whether a key exists without printing it:

```bash
uv run python -c 'import keyring; print("present" if keyring.get_password("aol-llm.anthropic", "api_key") else "missing")'
```

### Settings Shortcut Opens Terminal Settings

The app uses `f1` for settings. Older builds used `ctrl+,`, which may conflict
with terminal emulator preferences.

### Provider Errors

Provider errors appear in the transcript/status area. If a response fails after
your user message is saved, use `f7` to retry the last response.

### No Desktop Launcher Yet

The app currently runs as a terminal program through `uv run aol-llm` or
`uv run python -m aol_llm`. A bundled desktop launcher is a future packaging
task, not part of the first public iteration.
