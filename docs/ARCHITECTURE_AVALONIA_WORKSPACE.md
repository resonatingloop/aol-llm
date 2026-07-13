# Avalonia Workspace Architecture

Status: provisional architecture note, 2026-07-13. This records a preferred
direction for future exploration, not an implementation plan or approval to add
an Avalonia project, transport dependency, migration, or interface change.

## Purpose

THRESHOLD36 has a working Textual shell over a Python backend. A future Avalonia
shell should reuse it rather than reproduce storage, provider, pricing, prompt,
or memory behavior in C#.

The stateless generation facade gives non-UI consumers, including Discord
orchestration, a smaller reuse boundary. The proposed session should therefore
coordinate a desktop workspace, not become a universal LLM framework.

## Current Backend Shape

The useful boundaries now form two branches over shared provider-neutral code:

```text
Textual ----+
            +-> future DesktopWorkspaceSession -> ChatService
Avalonia ---+                                      +-> storage
                                                    +-> prompt assembly
                                                    +-> memory distillation
                                                    +-> pricing
                                                    +-> provider adapters

Discord and other non-UI consumers -> generate() -------> provider adapters

Shared foundations: core requests, types, errors, pricing, and provider adapters.
```

### Stateless generation

`src/aol_llm/generation.py` accepts an explicit `ProviderConfig`, API key, and
`NormalizedChatRequest`. It collects a provider stream into a complete
`GenerationResult` containing text, usage, cost, and requested-versus-reported
provider provenance.

It intentionally owns no persistence, prompt assembly, secret lookup, retry,
or UI behavior. It is suitable for consumers that own their own conversation
and participant semantics. It is not a desktop session and does not replace
`ChatService`.

The facade currently collects a complete response. The desktop chat path must
retain incremental streaming, so `ChatService` should not be forced through
`generate()` merely to remove similar provider-loop code.

### Persisted chat orchestration

`src/aol_llm/chat.py` remains the backend facade for THRESHOLD36 conversations.
It owns storage mutations, provider construction, prompt resolution, memory
injection, pricing, assistant-message persistence, retry, exports, and memory
distillation delegation.

SQLite, prompt versions, memory documents, provider adapters, and cost
calculation remain backend-owned. Neither Textual nor Avalonia should manipulate
those layers directly.

### Textual coordination pressure

`src/aol_llm/ui/app.py` currently combines Textual mechanics with state and
workflow decisions that another desktop shell would otherwise have to repeat:

- active buddy and conversation selection;
- default-conversation creation and selection fallback;
- send and per-buddy distillation busy state;
- lifecycle-triggered distillation on switches, archive, and quit;
- transcript, usage, reply-name, and memory-status projection;
- semantic action routing alongside Textual dialogs and notifications.

## Revised Direction: DesktopWorkspaceSession

The preferred candidate is a small stateful layer above `ChatService`. A name
such as `DesktopWorkspaceSession` or `ChatWorkspace` is more accurate than the
generic `ApplicationSession`.

The workspace would represent one running desktop client's selection and
operation state. It would expose UI-neutral snapshots and typed events while
delegating persisted chat behavior to `ChatService`.

### Responsibilities

The workspace is a reasonable home for:

- selected buddy and conversation identifiers;
- shared selection and fallback rules;
- single-flight send and distillation guards;
- shared lifecycle policy for switch-triggered distillation;
- resolved transcript, reply-name, usage, and memory read models;
- semantic operation results and UI-neutral error states;
- assistant delta and completion events for streaming shells.

### Explicit non-responsibilities

The workspace should not own:

- provider construction or provider-specific request behavior;
- API keys, keyring access, or provider configuration storage;
- SQLite queries or mutations outside `ChatService`;
- prompt assembly, memory rewriting, or pricing;
- Textual widgets, Avalonia view models, dialogs, focus, or clipboard behavior;
- user-facing labels, palette values, or rite-specific terminology;
- generic Discord participants, scheduling, or group-chat orchestration;
- a local transport protocol.

## Shell Usage

### Textual

Textual would remain an in-process Python shell. It would send semantic intents
to the workspace and render snapshots or events. Textual would continue to own
keybindings, slash syntax, command-palette integration, modal confirmation,
notifications, clipboard access, scrolling, focus, and styling.

The existing TUI should remain operational throughout any extraction and does
not need to communicate through localhost merely to prove the boundary.

### Avalonia

Avalonia would eventually launch or connect to a local Python backend and map
workspace snapshots into C# view models. Streaming events would update the
transcript without giving C# direct access to providers or SQLite.

The transport is intentionally undecided. HTTP plus a streaming response is
C#-friendly, while a child-process protocol may simplify local packaging. That
choice should follow a stable workspace contract rather than define it.

### Discord and other consumers

Non-desktop consumers should use `generate()` and own their room, participant,
scheduling, and persistence semantics. They should not depend on the desktop
workspace simply because both systems generate LLM responses.

## AIM-Style Concept Mapping

The workspace can expose the current model through presentation-neutral read
models without requiring immediate schema changes:

- **Buddy/contact identity:** buddy ID, name, and screen name.
- **Provider/model body:** provider and model fields presented separately from
  display identity, although they remain stored on `Buddy` today.
- **Reply identity:** conversation override, then buddy screen name, then the
  internal assistant fallback.
- **A-way message:** resolved prompt/version summary and generation provenance.
- **Room:** conversation, ordered messages, resolved identity, and aggregate
  usage.
- **Memory:** status, document, watermark, and distillation history queried
  through the backend.
- **Semantic actions:** invariant identifiers such as `conversation.archive` or
  `memory.disable`, independently labeled by each shell.

`Buddy` still combines contact identity with provider/model and prompt binding.
Separating a durable contact from an interchangeable model body would be a
future contract and schema decision, not part of extracting the workspace.

## Future Rite Overlay Socket

A future rite overlay has two different concerns and should not become a second
application mode.

Surface changes such as palette, labels, and visual emphasis belong entirely to
the shell. Stable semantic action identifiers let either shell change visible
language without changing backend behavior.

Any prompt-affecting overlay must enter through an explicit backend send
operation and be assembled by `prompt_assembly.py`. The GUI must not alter a
provider payload directly. Ordering, cache effects, provenance, and persistence
for such a prompt layer remain future contract decisions. No rite overlay needs
to be implemented to preserve this boundary.

## Risks And Guardrails

- A workspace that carries presentation strings or layout state becomes a
  Python view model and will duplicate Avalonia.
- A workspace marketed as the common abstraction for Discord and desktop chat
  will accumulate unrelated participant and lifecycle semantics.
- A transport defined before the workspace behavior stabilizes will harden
  accidental Python details into a cross-language API.
- `ProviderResponseMetadata` is available on final provider chunks, but
  `ChatService` does not currently propagate it through `ChatEvent` or storage.
  Desktop visibility and persistence are separate future decisions.
- Multiple shells or concurrent requests would require explicit operation
  ownership and cancellation behavior; current Textual flags are process-local
  UI state.
- Contact/body separation remains unresolved and must not be smuggled into a
  shell refactor.

## Provisional Recommendation

Keep the stateless generation facade as the reusable boundary for Discord and
other non-UI consumers. For Avalonia preparation, prefer a narrowly scoped
desktop workspace above the existing `ChatService`, with Textual as its first
adapter and a local transport added only when Avalonia work actually begins.

This direction preserves the working TUI and backend contracts while removing
the desktop workflow decisions that would otherwise be duplicated in C#.
