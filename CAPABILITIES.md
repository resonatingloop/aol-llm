# aol-llm capabilities

This is an index, not an inventory: it claims completeness of listing and owner
vocabulary, not accuracy of description. Each row is one unit a migration or
rework could plausibly drop, merge, or move — one row here is one row of a
future migration matrix (the planned desktop-shell migration is the first
consumer, with significant feature rework after). The **Aliases** column is the
join key from owner vocabulary to capability; the **Where** column is
best-effort and is allowed to drift, because file locations are cheap to
re-derive and exhaustive capability listing is not. Update it by diffing what
actually shipped in the cycle, not by re-describing the app from memory. When
this file disagrees with `CONTRACTS.md`, `README.md`, or the manual,
`CONTRACTS.md` owns the disputed fact.

Standing boundaries (not capabilities): memory is completely disabled (no
injection, no distillation, no memory model calls; see the disabled memory
contract in `CONTRACTS.md`). The app is local-first and offline: config, SQLite
history, and keyring secrets stay on the machine; chat sending never hits the
network for pricing. No cloud sync, accounts, or plugin system (PROJECT_BRIEF
non-goals).

`tests/test_docs_contracts.py` does not currently enforce this file; it is
maintained like the manual documentation-drift audit in `CONTRACTS.md`.

## Shell and navigation

| Aliases | Capability | Where |
|---|---|---|
| the TUI, MainScreen | Run a Textual main screen: Buddy List sidebar, selected-buddy Chats list, central transcript, bottom composer, status bar. | `src/aol_llm/ui/screens.py`, `widgets.py` |
| keybindings | Navigate by key: `f1` settings, `f2` rename buddy, `f3` send, `f4` new chat, `f5` archive, `f6` delete, `f7` retry, `ctrl+o` attach, `ctrl+v` paste, `ctrl+c` quit, `escape` close/cancel. | `src/aol_llm/ui/styles.py` `APP_BINDINGS` |
| slash commands | Run local composer commands that are not persisted as messages: `/cache`, `/help`, `/copy`, `/export`, `/away`, `/memory status`, `/attach`, `/paste`, `/detach`, `/buddy`, `/chatname`, `/quit`, `/settings`. | `src/aol_llm/ui/commands.py` |
| settings screen | Change the current chat's reply name; provider config and keys remain manual. | `src/aol_llm/ui/screens.py` `SettingsScreen` |
| confirmation | Confirm destructive operations through a generic yes/no modal. | `src/aol_llm/ui/modals.py` `ConfirmModal` |
| model picker | Switch model mid-chat from a modal. | `src/aol_llm/ui/modals.py` `ModelPickerModal` |
| buddy picker | Switch the active buddy from `/buddy`. | `src/aol_llm/ui/modals.py` `BuddyPickerModal` |
| rename buddy | Rename the active buddy (`f2`). | `src/aol_llm/ui/commands.py` |
| chatname | Edit the current chat's title (`/chatname`). | `src/aol_llm/ui/commands.py` |
| help | Show the current command summary (`/help`). | `src/aol_llm/ui/commands.py` |

## Chat

| Aliases | Capability | Where |
|---|---|---|
| composer | Compose multi-line input (`enter` continues editing) and send with `f3`. | `src/aol_llm/ui/widgets.py` |
| streaming | Stream assistant responses into the transcript as they arrive, scrolling to the bottom. | `src/aol_llm/ui/widgets.py` `ChatTranscript` |
| new chat | Start a new chat (`f4`). | `src/aol_llm/ui/` |
| archive chat | Archive the current chat (`f5`). | `src/aol_llm/storage/db.py` |
| delete chat | Delete the current chat with confirmation (`f6`); cascade removes its messages and stored images. | `src/aol_llm/storage/db.py` |
| retry | Retry the last response (`f7`), including previously stored image snapshots. | `src/aol_llm/chat.py` |
| a-way, away message | Edit a per-conversation a-way message (`/away`); it is stored on the conversation, not as a message, and applies to future sends. | `src/aol_llm/ui/commands.py`, `prompt_assembly.py` |
| reply name | Override the assistant display name for the current chat (`f1`); presentation metadata only, never changes stored roles or provider requests. | `src/aol_llm/ui/screens.py`, migration `004_conversation_assistant_name.sql` |
| prompt resolution | Resolve the effective prompt by chain: transient prompt version, then `conversation.prompt_version_id`, then buddy's version, then legacy `conversation.system_prompt`. | `src/aol_llm/prompt_assembly.py` |
| prompt versions | Keep cross-buddy away-message prompt cards with immutable versions; assistant messages record the exact prompt version used at generation. | `src/aol_llm/storage/db.py`, migration `002_buddies_prompts.sql` |
| buddy seeding | Seed default buddy/prompt on first run; startup never replaces an archived matching buddy for a provider/model pair. | `src/aol_llm/storage/db.py` |
| error surfacing | Translate provider failures into a readable status/transcript message and offer retry; no silent swallowing. | `src/aol_llm/core/errors.py` |

## Providers

| Aliases | Capability | Where |
|---|---|---|
| Anthropic adapter | Stream from the native Anthropic Messages API. | `src/aol_llm/providers/anthropic.py` |
| OpenAI-compatible adapter | Stream from OpenAI-compatible Chat Completions endpoints (built-ins: `openai`, `mistral`, `xai`). | `src/aol_llm/providers/openai_compat.py`, `registry.py` |
| Responses API mode | Opt into the OpenAI Responses API for provider-specific controls (verbosity, reasoning effort). | `src/aol_llm/providers/openai_responses.py` |
| adapter boundary | Keep provider-native objects out of UI, storage, and core; providers translate sdk errors into the error taxonomy at their boundary. | `src/aol_llm/providers/base.py` |

## Cost and caching

| Aliases | Capability | Where |
|---|---|---|
| token/cost totals | Show running token and estimated-cost totals in the status bar; persist per-message usage and cost. | `src/aol_llm/ui/widgets.py` `StatusBar`, `storage/db.py` |
| rate card | Estimate cost from the committed LiteLLM-derived pricing snapshot at send time, never from the network; unpriced models return `None`. | `src/aol_llm/core/pricing.py`, `data/model_prices.json`, `scripts/refresh_pricing.py` |
| cache normalization | Normalize Anthropic 5m/1h cache creation and cache reads, and OpenAI cache writes/reads, into disjoint `TokenUsage` buckets with no double counting. | `src/aol_llm/providers/`, `core/pricing.py` |
| prompt caching | Control Claude automatic prompt caching per conversation: `/cache on|1h|5m|off|status`; footer shows reads `r`, 5-minute writes `w5`, one-hour writes `w1h`. | `src/aol_llm/chat.py`, `providers/anthropic.py` |

## Images

| Aliases | Capability | Where |
|---|---|---|
| attach | Attach an image via file picker or `/attach PATH` (`ctrl+o`). | `src/aol_llm/ui/image_picker.py` |
| paste image | Paste an image from the desktop clipboard (`ctrl+v`), via `wl-paste` on Wayland, `xclip` on X11, or a dependency-free libX11 fallback; reads are bounded to five seconds and never take clipboard ownership. | `src/aol_llm/clipboard.py`, `_x11_clipboard.py` |
| queued images | Queue draft attachments per chat (shown above the composer); drafts survive chat switches, are not persisted until send, and are discarded on quit; `/detach` clears them. | `src/aol_llm/ui/` |
| image limits | Accept PNG, JPEG, GIF, and WebP detected from bytes, bounded to 5 MiB each, 10 images, and 20 MiB total per message; validation happens before HTTP and never silently converts to a text-only request. | `src/aol_llm/core/images.py` |
| image persistence | Snapshot image bytes into SQLite on send; later turns and `f7` retries use stored snapshots; deleting a chat deletes its images. | migration `009_message_images.sql`, `storage/db.py` |
| image transmission | Send user-message images as Anthropic base64 source blocks, compatible `image_url` data URIs, or Responses `input_image` data URIs, preceding text; only user messages carry images. | `src/aol_llm/providers/images.py` |
| export images | Export images as base64 data in JSON or a linked companion images folder beside Markdown exports. | `src/aol_llm/export.py` |

## Export and clipboard

| Aliases | Capability | Where |
|---|---|---|
| export | Export the current chat to Markdown or JSON (`/export`) into a chosen destination folder; the browser starts at home each time, the destination is never remembered, and cancel writes nothing. | `src/aol_llm/export.py`, `ui/` |
| copy pair | Copy the last prompt + response pair of the active chat to the clipboard (`/copy`). | `src/aol_llm/ui/commands.py` |

## Storage, secrets, config

| Aliases | Capability | Where |
|---|---|---|
| the db | Store all state in local SQLite at `~/.local/share/aol-llm/aol-llm.db`: conversations, messages, buddies, prompts and versions, providers, app settings, buddy memories, distill run ledger, and image blobs; migrations `001`–`009`. | `src/aol_llm/storage/db.py`, `storage/migrations/` |
| keyring | Read API keys from the system keyring under `aol-llm.<provider_id>` / `api_key`; keys are never written to config or disk. | `src/aol_llm/secrets.py` |
| config.toml | Read provider and UI defaults from `~/.config/aol-llm/config.toml`; the legacy `[memory]` section round-trips but cannot enable the disabled feature. | `src/aol_llm/config.py` |

## Memory boundary

| Aliases | Capability | Where |
|---|---|---|
| memory disabled | Report that memory is completely disabled: no injection, no automatic or manual distillation; `/memory status` and the footer say so; legacy memory rows and ledgers are retained on disk unused. | `src/aol_llm/memory_distiller.py`, `prompt_assembly.py`, `tests/test_memory_disabled.py` |
| backlog baseline | Owner-run utility to abandon a selected historical memory backlog in one transaction (dry-run default; apply requires an explicit verified backup path). | `scripts/baseline_memory_backlog.py` |

## Headless facade

| Aliases | Capability | Where |
|---|---|---|
| generate() | Stateless generation facade for non-Textual consumers: takes an explicit provider config, key, and request; returns one complete frozen result with usage, cost, and provider-reported metadata; imports no UI. | `src/aol_llm/generation.py` |
