# Memory Distiller Recovery

> **Status:** accepted
> **Accepted:** 2026-07-21
> **Owner decision:** abandon the four failed historical buddy backlogs as
> memory input while preserving every conversation and message.

## Context

The live database shows that large buddy histories repeatedly exhaust the
Opus 4.8 distiller's 4,096-token output budget without producing a visible
memory document. Validation correctly rejects those responses, but the
watermark remains unset and later lifecycle triggers retry the same backlog.

This slice restores useful forward memory without reprocessing the four failed
historical backlogs. It separates ordinary chat request behavior from
distiller request behavior, pauses automatic retries after invalid output, and
adds an explicit owner-operated recovery boundary.

## Change Shape

| Dimension | Changed? | Source of truth | Proof |
| --- | ---: | --- | --- |
| User-visible behavior | yes | memory status and notifications | chat-service tests and manual UI inspection |
| Persisted state or schema | state only; no schema change | `buddy_memories` watermarks | storage tests and live verification |
| External or provider-visible behavior | yes | Anthropic distiller request | mocked request test |
| Identifiers, secrets, or privacy | no new identifiers or secrets | existing private buddy ids | review and private backup |
| Lifecycle or terminal states | yes | automatic distill pause | switch/quit tests |
| Setup, operation, or recovery | yes | recovery utility and user manual | dry run, backup, and restore proof |
| Normative contract or decision | yes | `CONTRACTS.md` | docs-contract tests and review |
| Cross-repository dependency | no | n/a | review |

## Scope

### In scope

- Preserve adaptive thinking for ordinary Opus 4.8 chat requests.
- Omit adaptive thinking from Anthropic distiller requests.
- Pause automatic distillation when the latest provider-attempted run failed
  validation; a no-op does not clear the pause.
- Keep manual `/memory distill` as the explicit retry path. A successful manual
  distill clears the pause.
- Surface the paused failure state in memory status.
- Add a guarded, owner-operated recovery utility that can baseline only
  buddies whose memory document is absent or empty.
- Baseline a selected buddy at its lexicographically newest stored message,
  leaving its memory empty and its conversations/messages untouched.
- Dry-run and back up the live database before any baseline is applied.

### Out of scope

- Changing `/memory off`; it remains injection-only.
- Reprocessing the four abandoned historical backlogs.
- Changing per-buddy memory scope, batch size, prompt wording, or distiller
  model defaults.
- Mid-conversation memory reload.
- Existing buddy histories that have never failed distillation.
- Delete-renunciation implementation.

## Invariants

1. The shared `Provider.stream(...)` signature does not change.
2. Ordinary Opus 4.8 chat requests retain adaptive thinking.
3. Distiller traffic still uses the configured provider adapter, pricing, and
   run ledger; only Anthropic thinking behavior differs.
4. One invalid-output failure may record one failed run. Later automatic
   switch/archive/quit triggers make zero provider calls until a manual
   distill succeeds.
5. A no-op does not erase an earlier invalid-output pause.
6. A paused quit exits normally without a provider call.
7. Baseline recovery refuses non-empty memory documents and buddies without
   messages.
8. Baseline recovery changes only `buddy_memories`: text stays empty, the
   enabled flag is preserved, suppression is cleared, and the watermark moves
   to the newest stored message.
9. Baseline recovery does not create a successful distill ledger row.
10. Live recovery is reversible through a private SQLite backup and requires a
    separate owner checkpoint before apply.

## Implementation Map

- `src/aol_llm/providers/anthropic.py`: construction-time adaptive-thinking
  control, defaulting to current chat behavior.
- `src/aol_llm/providers/registry.py`: narrow distiller provider constructor.
- `src/aol_llm/memory_distiller.py`: use the distiller constructor by default.
- `src/aol_llm/storage/db.py`: latest attempted-run lookup and guarded baseline
  transaction.
- `src/aol_llm/chat.py`: computed auto-pause state and memory status.
- `src/aol_llm/ui/app.py`: automatic-trigger gate; manual trigger bypass.
- `scripts/baseline_memory_backlog.py`: stdlib dry-run/apply recovery surface.
- Provider, distiller, storage, and chat-service tests; manual lifecycle UI inspection.
- `CONTRACTS.md`, `docs/USER_MANUAL.md`, and `docs/CODEBASE_SCHEMA.md`.

## Acceptance Criteria

- Mocked ordinary Opus request includes `thinking: {"type": "adaptive"}`.
- Mocked Opus distiller request omits `thinking` and returns a valid memory doc.
- Invalid output pauses later automatic triggers without adding run-ledger or
  cost entries; manual success re-enables them.
- Recovery dry-run reports targets without writing. Apply requires explicit
  intent and creates a private backup before changing the database.
- On a temporary database, baseline leaves transcript counts unchanged and
  makes the target's pending-message count zero.
- On the live database, the dry run selects exactly the four owner-approved
  failed histories. Execution stops before apply for owner confirmation.
- After apply, one new manual canary distill succeeds before automatic
  distillation is trusted again.

## Validation

```bash
uv run python -m pytest
uv run ruff check
uv run ruff format --check
uv run python -m mypy --strict src tests
python3 /home/resonatingloop/.codex/skills/manage-project-docs/scripts/check_docset.py . --require PROJECT_BRIEF.md --require CONTRACTS.md --review-claims
git diff --check
```

The repository-wide Ruff commands currently encounter the pre-existing,
ignored root `db.py` scratch file. That file is outside this slice and must not
be modified silently; scoped `src tests scripts` checks remain required if the
owner leaves it in place.
