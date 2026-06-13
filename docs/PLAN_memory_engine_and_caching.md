# Memory Engine + Prompt Cache Integration Plan

This plan implements `docs/SPEC_memory_engine_and_caching.md` with the
amendments in `docs/SPEC_amendments_slices_1_4_5.md`.

## Ground Rules

- Memory is per-buddy only.
- Memory text is plaintext markdown, directly viewable and editable.
- Distiller calls route through existing provider adapters and cost recording.
  Hard budget enforcement is out of scope for v1.
- Anthropic cache markers stay inside the Anthropic adapter. OpenAI-compatible
  providers receive ordinary system content only.
- No volatile per-call content may enter tools/system before a cache breakpoint.
- Delete is renunciation: deleted conversation content must be removed from
  local transcript and rebuilt memory. Remote provider cache TTLs are outside
  app control.

## Open Decisions Resolved

- Distiller prompt lives as package data:
  `src/aol_llm/data/memory_distiller_prompt.md`.
- Cache TTL remains global for v1.
- Persist cache token breakdown columns now.
- No mid-conversation memory reload in v1.
- No pre-warm in v1.
- Watermark order is total and lexicographic: `(created_at, message_id)`.
- Distiller default is `anthropic / claude-sonnet-4-6`; haiku and opus remain
  configurable for comparison.

## Slice 0: Contract Correction

Goal: remove Anthropic cache concepts from the shared provider protocol.

Files:
- `src/aol_llm/core/types.py`
- `src/aol_llm/providers/base.py`
- `src/aol_llm/providers/registry.py`
- `src/aol_llm/providers/anthropic.py`
- `src/aol_llm/providers/openai_compat.py`
- `src/aol_llm/chat.py`
- `CONTRACTS.md`
- provider/chat/core tests

Changes:
- Remove `PromptCacheControl` from canonical core dataclasses.
- Remove `prompt_cache` from `Provider.stream(...)`.
- Make Anthropic cache TTL an Anthropic provider construction concern.
- Keep OpenAI-compatible provider signatures free of cache parameters.
- Preserve existing `/cache` behavior and Anthropic top-level automatic caching.

## Slice 1: Schema + Storage

Migration `006_buddy_memories_and_cache_usage.sql`.

Add `buddy_memories`:
- `buddy_id TEXT PRIMARY KEY REFERENCES buddies(id) ON DELETE CASCADE`
- `memory_text TEXT NOT NULL DEFAULT ''`
- `enabled INTEGER NOT NULL DEFAULT 1`
- `suppress_injection INTEGER NOT NULL DEFAULT 0`
- `watermark_created_at TEXT`
- `watermark_message_id TEXT`
- `updated_at TEXT NOT NULL`

Add nullable message cache columns:
- `cache_creation_5m_input_tokens INTEGER`
- `cache_creation_1h_input_tokens INTEGER`
- `cache_read_input_tokens INTEGER`

Rules:
- `NULL` means provider did not report the token class.
- `0` means provider reported zero.
- Newer-than-watermark query uses strict lexicographic order:
  `created_at > watermark_created_at OR
  (created_at = watermark_created_at AND id > watermark_message_id)`.
- Add haiku-class pricing entries while touching pricing ingestion.

Tests:
- migration shape and FK behavior
- cache column NULL vs zero
- per-buddy memory isolation
- total-order watermark determinism across interleaved conversations

## Slice 2: Prefix Assembly Layer

Add `src/aol_llm/prompt_assembly.py`.

Assembly output:
1. stable system blocks:
   - away message
   - memory document with clear heading/delimiter
2. stored messages in order
3. provider adapter emits cache markers conditionally

Memory injection predicate:
- row exists
- `enabled = 1`
- `memory_text.strip()` is non-empty
- `suppress_injection = 0`

If any condition fails, inject no memory block: no heading, delimiter, or
placeholder.

Tests:
- no row injects nothing
- disabled row injects nothing
- empty/whitespace row injects nothing
- suppressed row injects nothing
- positive memory row injects memory block
- stable serialized system prefix across consecutive turns
- OpenAI-compatible payload has plain flattened system text
- Anthropic payload has explicit last-system-block cache marker plus top-level
  automatic cache when cache is enabled

## Slice 3: Memory Repository + Injection

Add repository functions:
- `get_buddy_memory`
- `upsert_buddy_memory`
- `set_buddy_memory_enabled`
- `set_buddy_memory_suppressed`
- `clear_buddy_memory`
- `messages_newer_than_watermark_for_buddy`

Wire assembly into chat sends, but do not add the distiller yet.

## Slice 4: TUI Memory Commands

Commands:
- `/memory view`
- `/memory edit`
- `/memory on`
- `/memory off`
- `/memory forget`

UX:
- Use an in-TUI `TextArea` modal for edit. Do not rely on `$EDITOR`.
- `/memory forget` is destructive and uses confirmation.
- Footer indicates memory enabled/disabled, present/empty, approximate size,
  suppressed state, and distilling state when applicable.

## Slice 5: Distiller

Add:
- `src/aol_llm/memory_distiller.py`
- `src/aol_llm/data/memory_distiller_prompt.md`

Distiller behavior:
- Input: current memory doc plus transcript slice newer than watermark.
- Output: full rewritten memory document.
- Each batch transactionally commits memory replacement and watermark advance.
- Failed/cancelled batch leaves the previous committed doc intact.
- Full redistill is the same incremental loop from null watermark, oldest-first.
- Suggested transcript batch bound: roughly 20-30k tokens, tunable.

Prompt skeleton:
- `## current state`
- `## standing decisions`
- `## open threads`
- `## preferences & conventions`

Negative instructions:
- no first person
- no buddy diary voice
- no flattery
- no user personality summaries
- no vague affect labels

Config:
- `[memory].distiller_provider`
- `[memory].distiller_model`
- defaults: `anthropic`, `claude-sonnet-4-6`

Manual trigger:
- `/memory distill`

Tests:
- fake provider distill success
- transactional failure
- batched full-redistill reuses incremental codepath
- no API call when no messages are newer than watermark

## Slice 6: Auto Distill Triggers

Auto-trigger distillation on:
- conversation switch: distill the conversation being switched away from
- app quit: distill active conversation
- archive: distill archived conversation

All auto-triggers are watermark-guarded. No new messages means no provider call.
Background async work should be owned by the Textual app/service orchestration,
not silently spawned from storage.

## Slice 7: Delete Renunciation

Delete flow:
1. Identify the conversation's buddy.
2. Determine whether any deleted message is at or before the buddy watermark.
3. Clean case: all deleted messages are newer than watermark.
   - delete only
   - no redistill
   - memory doc remains byte-identical
4. Metabolized case: any deleted message is at or before watermark.
   - reset watermark to null
   - set `suppress_injection = 1`
   - delete conversation
   - launch background batched redistill from surviving buddy history
   - when complete, atomically write rebuilt memory and lift suppression

Comment the boundary: app deletion cannot purge still-warm Anthropic prompt
caches before provider TTL expiry.

Tests:
- clean delete triggers no redistill and leaves memory unchanged
- metabolized delete suppresses injection immediately
- rebuilt doc excludes deleted content

## Final Validation Per Slice

Run after each slice:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict src tests
```

Also run docs drift checks through the full test suite and manually audit
`PROJECT_BRIEF.md`, `CONTRACTS.md`, README/manual accuracy, provider/pricing
claims, and known drift notes.
