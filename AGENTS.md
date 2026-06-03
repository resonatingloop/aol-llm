# AGENTS.md

This file governs the behavior of AI coding agents (Codex, Claude Code, etc.) working in this repository. Read it at the start of every session before doing anything else.

## Project Context

aol-llm is a personal Linux desktop chat client for talking to multiple LLM providers through one interface. v0 ships as a Textual TUI; a richer GUI is a possible future pass. It is a hobby project — not enterprise software. Prefer simple, boring, reversible decisions. There is one user. There is no production. There is no team.

## Required Reading

Before acting on any task, the agent MUST have read:
1. `PROJECT_BRIEF.md` — product direction, MVP scope, build plan
2. `CONTRACTS.md` — data models, provider interface, schema, error taxonomy
3. This file

If any of these contradicts the task as requested, stop and ask before proceeding.

## Operating Rules

**Scope discipline.** Do exactly the task assigned. No "while I'm here" refactors, no opportunistic cleanups, no renaming unrelated files. If you notice a problem outside the current task and you are already modifying the affected file, leave a `# TODO(agent): <description>` comment. Otherwise, just report the observation verbally at the end of the session.

**One coherent unit per session.** A session implements one feature, refactor, or module. If the user's request implies multiple unrelated units, surface the breakdown and confirm before starting. Within a single coherent unit, do not stop to confirm each sub-step. An explicit "go implement X" or "proceed with X" from the user counts as confirmation of any plan you've already proposed in this conversation. Absent such explicit go-ahead, propose a plan and wait.

**Plan first, code second.** Before writing any code, restate the task and outline the changes you intend to make (files to touch, signatures to add or change, tests to write). Wait for confirmation before implementing.

**Dependencies require approval.** Do NOT add anything to `pyproject.toml` without explicit user approval. The current dependency set is intentional and minimal. If you believe a new dep is necessary, name it, justify it, and wait. This rule includes dev dependencies.

## Pre-Approved Dependencies

The following dependencies are already approved because this file, `PROJECT_BRIEF.md`,
or `CONTRACTS.md` requires them:

- `pytest`
- `pytest-asyncio`
- `respx`
- `ruff`
- `mypy`
- `platformdirs`

Agents may add these to `pyproject.toml` without asking. Any dependency beyond
this list still triggers the dependency approval rule.

**No silent invention.** If a contract is ambiguous (schema field type, error semantics, provider behavior on an edge case), stop and ask. Do not infer plausibly-correct behavior. Plausibly-correct is usually subtly wrong here.

**Boring choices.** Prefer stdlib over third party. Prefer dataclasses over pydantic. Prefer module-level functions over classes. Prefer explicit over clever. If you find yourself reaching for `metaclass=`, `__init_subclass__`, dynamic imports, monkey patching, or a decorator factory, stop and reconsider.

## Code Conventions

- **Python version**: 3.12 or newer. Use modern syntax (`list[str]`, `X | None`, pattern matching where it actually clarifies).
- **Type hints**: required on all function signatures and dataclass fields. Local variable annotations only when they materially clarify.
- **Data types**: `@dataclass(frozen=True)` for value types. No pydantic. No attrs. No `TypedDict` unless interfacing with external JSON.
- **Async**: provider code and HTTP are async. Storage is sync (sqlite, blocking is fine at this scale). Do not mix paradigms within a single module.
- **Errors**: raise specific subclasses of `ProviderError` at the provider boundary. Never `except Exception:` without re-raising. Never silently swallow.
- **Logging**: use stdlib `logging`. Never log API keys. Log message content only at `DEBUG` level. Default level is `INFO`.
- **Imports**: stdlib, third-party, local — separated by blank lines. No `from x import *`.
- **Files**: one coherent concern per file. Keep files under ~200 lines; split if growing past that.
- **Tooling**: code must pass `ruff check`, `ruff format --check`, and `mypy --strict` before any task is declared done.

## Testing Rules

- **Framework**: `pytest` with `pytest-asyncio` for async tests.
- **HTTP mocking**: `respx` (pre-approved dependency).
- **What is tested**: provider contract compliance, storage functions, error taxonomy, config/keyring access (keyring mocked).
- **What is not tested**: Textual UI behavior, exact wire format of provider requests beyond what the contract guarantees.
- **Run tests before declaring done.** A task is not complete until `pytest`, `ruff`, and `mypy` all pass clean.

## Git Conventions

- Commit per logical step, not per file.
- Commit messages: imperative present tense, lowercase, no period. Examples: `add anthropic provider`, `wire streaming into transcript`, `fix off-by-one in token accounting`.
- Do not commit secrets, generated files, or scratch files. Verify `.gitignore` first.
- Work directly on `main` unless explicitly told to branch.

## Session Protocol

**Start of session:**
1. Read `PROJECT_BRIEF.md`, `CONTRACTS.md`, `AGENTS.md`.
2. Run `git status` and confirm clean working tree (or surface any uncommitted state).
3. Acknowledge the assigned task in your own words.
4. Outline a plan and wait for confirmation.

**During implementation:**
- Implement one logical chunk at a time.
- Run tests and tooling after each chunk.
- After every implementation slice, run the docs drift checks in
  `tests/test_docs_contracts.py` as part of the test suite. These are not
  optional; they protect keybindings, provider defaults, keyring services,
  migrations, dataclass contracts, codebase schema coverage, validation command
  strings, and stale doc claims.
- Surface contract ambiguities the moment you encounter them, not at the end.

**End of session:**
1. Run full test suite, including `tests/test_docs_contracts.py`, plus ruff and
   mypy.
2. Perform the manual documentation drift audit listed in `CONTRACTS.md`, or ask
   the user to check any item that cannot be verified by the agent.
3. Summarize: files changed, tests added, manual docs-audit outcome, and any
   `TODO(agent):` markers left.
4. Propose a commit message.
5. Wait for instruction before pushing.

## Stop-and-Ask Triggers

Pause and ask explicitly if you encounter any of:
- A change to `PROJECT_BRIEF.md`, `CONTRACTS.md`, or this file.
- A schema migration (any change to existing tables, even "harmless" ones).
- A change to keyring service names (would orphan existing keys).
- A change to the provider interface signature.
- An ambiguous instruction admitting multiple reasonable interpretations.
- Discovery that the task as specified contradicts an existing contract.
- Anything you would describe as "I'll just" or "it should be fine to".

## Forbidden Without Explicit Approval

- Adding `pydantic`, `sqlmodel`, `sqlalchemy`, `click`, `typer`, `rich-cli`, or other "obvious" packages.
- Building a `BaseManager`, `AbstractRepository`, or any other premature abstraction.
- Threads, multiprocessing, `concurrent.futures` (we are async).
- Catching broad exceptions to make tests pass.
- Writing UI tests for Textual (out of scope for v0).
- Refactoring outside the current task's scope.
- "Improving" `PROJECT_BRIEF.md` or `CONTRACTS.md` without being asked.
- Adding configuration knobs nobody requested. YAGNI is the default.
- Module-level mutable state, import-order-dependent initialization, global singletons.

## Notes for Humans

- This file is short on purpose. If a rule is missing and an agent does something unwanted, the rule was missing — add it here rather than reprimanding ad hoc.
- When agent behavior seems wrong systemically, ask the agent to read this file aloud and explain how it interpreted each rule. Drift usually surfaces immediately.
