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
the default OpenAI-compatible configs, those are:

```text
service:  aol-llm.openai
username: api_key

service:  aol-llm.mistral
username: api_key

service:  aol-llm.xai
username: api_key
```

Set those keys with:

```bash
uv run python -c 'import keyring; keyring.set_password("aol-llm.openai", "api_key", "YOUR_KEY_HERE")'
uv run python -c 'import keyring; keyring.set_password("aol-llm.mistral", "api_key", "YOUR_KEY_HERE")'
uv run python -c 'import keyring; keyring.set_password("aol-llm.xai", "api_key", "YOUR_KEY_HERE")'
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

Type a message in the composer and send it with `f3`. Regular `enter`
continues editing in the composer.

The settings screen can update the reply name used by the current chat.
Provider config and API keys are still edited manually for now.

## Slash Commands

Slash commands run from the composer with `f3`. They are local app commands and
are not saved as chat messages.

<!-- BEGIN AUTOGEN:slash-commands-table -->
| Command | Action |
| --- | --- |
| `/cache on` | Enable one-hour Claude prompt caching |
| `/cache 1h` | Enable one-hour Claude prompt caching |
| `/cache 5m` | Enable five-minute Claude prompt caching |
| `/cache off` | Disable Claude prompt caching |
| `/cache status` | Show whether Claude prompt caching is enabled |
| `/help` | Show the current command summary |
| `/copy` | Copy last prompt + response pair in active chat to clipboard |
| `/export` | Open export menu |
| `/away` | Open a-way menu |
| `/memory status` | Show that memory is disabled |
| `/attach` | Choose an image file (or /attach PATH) |
| `/paste` | Paste an image from the desktop clipboard |
| `/detach` | Clear the current chat's queued images |
| `/buddy` | Open active buddy picker |
| `/chatname` | Open current chat name editor |
| `/quit` | Quit |
| `/settings` | Open settings |
<!-- END AUTOGEN:slash-commands-table -->

Prompt caching only affects Anthropic/Claude requests. When enabled, the app
uses Claude's automatic ephemeral prompt caching for future sends. The status
footer shows cache reads as `r`, five-minute writes as `w5`, and one-hour writes
as `w1h`.

## Memory Is Disabled

Memory injection and distillation are completely disabled. Changing chats,
buddies, or models, archiving, and quitting never trigger memory model calls.
All `/memory` commands report that memory is disabled; even `/memory on` cannot
enable it. Existing memories and chat history are retained. Legacy `[memory]`
config values cannot enable the feature. Restart an already-running app to load
the changed code.

## Sending Images

Use the **Attach image** button, `ctrl+o`, or `/attach` to open a file picker.
Browse from your home directory or type a full path. `/attach PATH` also works;
paths containing spaces can be quoted or entered as-is.

Copy an image using your desktop application (for example Firefox's Copy Image),
then use **Paste image**, `ctrl+v`, or `/paste`. This reads binary image data from
the desktop clipboard; a copied URL or text is not an image. If your terminal
intercepts a shortcut, use the button or slash command. Normal terminal text
paste remains separate (typically `ctrl+shift+v`).

Clipboard import uses `wl-paste` on Wayland when available, `xclip` on X11 when
available, or a dependency-free libX11 fallback on X11/Xwayland. A pure Wayland
session without Xwayland needs the optional system `wl-clipboard` package. No
Python dependency is added, and clipboard contents are not changed by import.

Queued filenames appear above the composer. Add optional text and press `f3` to
send; an image-only message is supported. **Clear images** or `/detach` removes
the queued attachments. Draft images belong to their chat, remain queued when
switching chats, and are not persisted until sending. Closing the app discards
unsent draft images.

Supported formats: PNG, JPEG, GIF, WebP. Limits: 5 MiB per image, 10 images per
message, and 20 MiB total per message. Format is detected from bytes, not the
filename. File picking/pasting is local and makes no model call; sending an
image is part of the normal chat request and is billed by the chosen provider.
Choose a vision-capable model. Custom compatible endpoints may not support
images; their rejection is shown as a provider error, never silently converted
to a text-only request.

The app snapshots image bytes into SQLite when sending. Later turns and `f7`
retries include those saved images even if the original file is moved/deleted.
The TUI shows filenames, not graphical previews. Deleting a chat also deletes
its stored attachments. JSON exports include base64 image data; Markdown exports
write a linked companion images folder. Keep that folder with the `.md` file.

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
| `ctrl+o` | Attach image |
| `ctrl+v` | Paste image |
| `ctrl+c` | Quit |
<!-- END AUTOGEN:keybindings-table -->
| `escape` | Close settings or cancel a modal |

Destructive actions ask for confirmation first.

`f1` opens settings from the main screen and closes settings when pressed again.

## Reply Name

Use `f1` to open settings and change the reply name for the current chat. Blank
the field to follow the current buddy name.

This is local display text only. Stored messages still use the internal
`assistant` role, and provider requests are unchanged.

## a-way Messages

a-way messages are per-conversation. Use `/away` to edit the current
conversation's a-way. Save a blank a-way to clear it.

a-way messages are stored on the conversation record, not in the message list.
Future sends in that conversation use the saved a-way; existing messages are not
changed.

## Export

Use `/export` to export the current chat. Choose Markdown for a readable document
or JSON for structured data, then choose a destination folder in the browser.
The browser starts at your home directory each time. Cancel either step to write
nothing; the app does not remember an export destination.

## Local Files

The app follows XDG paths:

```text
Config: ~/.config/aol-llm/config.toml
Data:   ~/.local/share/aol-llm/
DB:     ~/.local/share/aol-llm/aol-llm.db
```

The database stores conversations, messages, provider rows, settings, token
usage, and estimated cost fields. API keys stay in keyring.

Estimated costs use the committed pricing snapshot at
`src/aol_llm/data/model_prices.json`. The app does not call the network for
pricing while chatting; models missing from the snapshot may show no cost until
the snapshot is refreshed.

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
