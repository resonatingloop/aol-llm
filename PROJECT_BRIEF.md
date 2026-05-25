# AOL-LLM Project Brief

## summary

AOL-LLM is a Linux desktop chat client for using multiple LLM providers through
one consistent local interface. The first build target is a Textual app that
proves the core workflow: configure providers, start chats, switch models,
stream responses, preserve conversation history, and inspect token/cost usage.

The long-term desktop target is intentionally undecided. Textual is the first
pass because it is fast to build, keyboard-friendly, and already fits the
current Python skeleton. After the Textual MVP proves the product workflow, the
project can stay Textual or move to PySide6 or Tauri 2.

## product goals

- Provide a unified chat client for Anthropic and OpenAI-compatible providers.
- Keep the app local-first: local config, local SQLite history, keyring secrets.
- Make model and provider switching explicit without hiding provider differences.
- Preserve useful chat history with exportable, inspectable data.
- Track tokens and estimated cost as a first-class part of each chat response.
- Build a project that can be packaged, documented, and shared on GitHub.

## provider framing

The provider model has two first-class families:

- `anthropic`: native Anthropic Messages API.
- `openai_compatible`: OpenAI-compatible API providers, starting with OpenAI and
  leaving room for local or hosted compatible endpoints later.

Provider adapters translate AOL-LLM's internal request shape into provider-native
API calls. Provider-native objects must not leak into UI, storage, or core app
code.

## system prompt contract

System prompts are stored on the conversation, not as messages. A conversation
has one canonical `system_prompt` field, and messages are limited to user and
assistant roles for normal chat storage.

Provider adapters receive the effective system prompt separately from ordered
user/assistant messages and translate it into each provider's required API
format. Imports or future compatibility layers may parse system-style content,
but normalized runtime storage keeps system prompt state on the conversation.

## technical contracts

Implementation details for canonical data types, provider boundaries, error
taxonomy, SQLite schema, storage functions, config/secrets, pricing, Textual UI
scope, and acceptance criteria live in [CONTRACTS.md](./CONTRACTS.md).

The brief defines what we are building and why. `CONTRACTS.md` defines the
stable interfaces we agree not to casually drift from during implementation.

## MVP scope

- Textual desktop/TUI app.
- Anthropic provider adapter.
- OpenAI-compatible provider adapter.
- Provider/model configuration.
- API key setup stored through `keyring`.
- Local SQLite storage for conversations, messages, providers, settings, and
  token/cost usage.
- Streaming chat UI with conversation list, transcript, composer, model picker,
  and status area.
- Retry last response from the UI.
- Export current chat to Markdown and/or JSON.
- README with install, run, configuration, and development instructions.

## non-goals for MVP

- Full native GUI.
- Cloud sync.
- User accounts.
- Plugin system.
- RAG or document indexing.
- Multi-agent workflows.
- Prompt marketplace.
- Automatic provider billing reconciliation.

## implementation plan

### 1. Establish project docs

Create `PROJECT_BRIEF.md` and refine `CONTRACTS.md` into stable source-of-truth
documents for the build.

Done when: both documents are committed-ready, the brief links to contracts, and
the contract file contains durable implementation decisions rather than draft
conversation notes.

### 2. Define core models and storage schema

Add canonical dataclasses, error taxonomy, provider config types, stream chunk
types, and the initial SQLite migration. Include token/cost fields in the schema
from the start.

Done when: core types are importable, frozen where appropriate, migrations exist,
and schema choices match `CONTRACTS.md`.

### 3. Add tests early

Add tests before building the full UI. Cover provider contracts, system prompt
translation, request normalization, storage migrations, repository behavior,
usage parsing, and cost calculation.

Done when: tests can run with `uv run pytest`, storage can be tested against a
temporary database, and mocked provider tests cover normal stream completion plus
representative provider errors.

### 4. Implement provider contracts

Build the shared provider protocol, Anthropic adapter, OpenAI-compatible adapter,
provider registry, and normalized streaming event format.

Done when: both provider families implement the same protocol, return normalized
stream chunks, translate provider errors into the app taxonomy, and pass contract
tests without live API calls.

### 5. Implement config and secrets

Use XDG paths for config and app data. Store non-secret provider defaults in
config and API keys in `keyring`.

Done when: config can be read/written, provider defaults can be resolved, API
keys never touch config or SQLite, and missing-key behavior is user-actionable.

### 6. Implement storage repositories

Build thin repository functions over stdlib `sqlite3` for conversations,
messages, providers, settings, and usage/cost updates.

Done when: migrations apply to a fresh database, foreign keys are enforced, basic
CRUD is covered by tests, and message deletion follows conversation cascade
rules.

### 7. Build Textual shell

Create the app shell with `MainScreen`, conversation list, transcript, composer,
status area, settings screen, model picker, and confirm modal.

Done when: the app launches, renders the core layout, accepts composer input,
registers keybindings, and can operate with stubbed data.

### 8. Wire streaming chat

Connect the UI to storage and providers. Sending a message should persist the
user message, stream the assistant response, save the assistant message, and log
tokens/cost.

Done when: `f5` sends a chat request, response text streams into the
transcript, final usage is recorded, and the status area updates token/cost
totals.

### 9. Add chat management

Add rename, archive/delete, retry last response, model switching, and export.

Done when: high-frequency chat actions work from keybindings and UI controls,
destructive actions confirm first, and exports are readable outside the app.

### 10. Prepare public GitHub release

Add README details, screenshots or terminal recordings, license, development
commands, package/build notes, and a release checklist.

Done when: a new user can clone the repo, install with documented commands,
configure at least one provider, run the app, and understand the project status.

### 11. Reassess desktop target

Evaluate whether Textual remains the right app shell or whether the proven
workflow should move to PySide6 or Tauri 2.

Done when: there is a written decision comparing implementation cost,
packaging friction, UI quality, Linux desktop integration, and expected user
workflow.

## dependency policy

The initial implementation should use the dependencies already listed in
`pyproject.toml` unless there is a specific reason to add one. Ask before adding
new dependencies.

## packaging direction

Start with Python packaging that works cleanly through `uv` and the project
script entrypoint. Public GitHub packaging should prioritize clear install/run
docs first, then evaluate binary or desktop-entry packaging once the Textual MVP
is useful.
