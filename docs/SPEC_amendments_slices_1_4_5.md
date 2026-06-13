# AIM Memory Engine — Plan Amendments (pre-slice-4/5)

Amends the implementation plan for `docs/SPEC_memory_engine_and_caching.md`. The plan's shape, slice 0 (contract correction), and slices 1–3 stand as written. These amendments resolve items left open or under-specified, and must be folded in **before** building slices 4 (distiller) and 5 (delete propagation). Keyed to the slice each touches. DECIDED items elsewhere in the brief are unchanged.

---

## Contract corrections (C4 / C5) — confirm and amend

Codex's read is correct: no budget-guard module exists; the repo has pricing/cost estimation only. The brief's references to a "budget guard" are aspirational. Amend rather than build one:

- **C4 (amended):** all distiller traffic routes through the existing provider adapter + pricing/cost-recording path, attributed per-buddy. No side-channel API calls. (Unchanged in spirit; "budget guard" → "pricing/cost-recording path.")
- **C5 (amended):** unpriced token classes — including cache classes — propagate as `None`/unknown in cost records. Cost estimation must never silently substitute a guessed rate without marking it as a fallback. **Hard budget enforcement (blocking sends over a limit) is out of scope for v1.** v1 prices and records; it does not block.

No prerequisite budget-guard slice. Defer hard limits to a future feature unless explicitly pulled in.

---

## Slice 1 (schema + storage) amendments

**S1-a. Watermark must define a total order.**
`messages_newer_than_watermark_for_buddy` spans conversations (memory is per-buddy), so ordering must be well-defined *across* conversations, not just within one. If message ids are non-monotonic (uuids), ordering by `created_at` alone is ambiguous on ties and interleaved threads, making distills nondeterministic and unreproducible.

- Define the order as lexicographic `(created_at, message_id)`.
- Store the watermark as that pair: `watermark_created_at` + `watermark_message_id` (already planned — this just fixes their *meaning*).
- "Newer than watermark" = strictly greater under that total order. Make the tiebreaker explicit in the query, not incidental to row insertion order.

**S1-b. Empty-doc is a real state; the injection predicate must handle it.**
`memory_text NOT NULL DEFAULT ''` permits a row that exists with empty text. Combined with cold start and mid-rebuild suppression (S5-a), there are four distinct "inject nothing" conditions. Collapse them into one predicate, used by the assembly layer (slice 2):

> Inject the memory block **only if** the row exists AND `enabled = 1` AND `memory_text` is non-empty after strip AND the buddy is not in rebuild-suppression. Otherwise inject nothing — no heading, no delimiter, no placeholder.

This is the same predicate the cold-start test in slice 2 already asserts; it just needs to also cover empty-string rows and the suppression flag.

**S1-c. Cache-breakdown columns: NULL means "not reported," never zero.**
The new `cache_creation_5m_input_tokens` / `cache_creation_1h_input_tokens` / `cache_read_input_tokens` columns must distinguish "provider did not report this class" (`NULL`) from "reported as zero" (`0`). OpenAI-compat rows are `NULL` across all three; an Anthropic uncached send is `0`. Cost aggregation and the difficulty-ratio analysis depend on not conflating them. One sentence in the migration comment; one check in the row mapper.

**S1-d. Do not add haiku-class rates for the distiller path.**
Haiku-class models are not expected to preserve enough detail for this memory
use case. The distiller remains configurable, but the planned default is
Opus-class and slice 1 should not add Haiku pricing solely for distillation.

---

## Slice 4 (distiller) amendments

**S4-a. Auto-distill triggers: switch + quit, not archive alone.**
"Conversation close = archive" will under-fire — conversations are far more often abandoned (switched away from, app quit) than explicitly archived. Archive-only makes the auto path decorative and `/memory distill` the de facto real mechanism, with memory perpetually lagging.

Auto-distill the relevant conversation on:
- conversation **switch** (distill the one being switched *away from*),
- app **quit** (distill the active conversation),
- archive (as already planned).

Every auto-trigger is **watermark-guarded**: if no messages exist newer than the buddy's watermark, it is a no-op with **no API call**. This makes generous triggers free when redundant, so over-firing costs nothing and under-firing is the only real failure mode. Manual `/memory distill` unchanged.

**S4-b. Distillation is batched; full redistill is the same codepath, looped.**
The distiller must process transcript in bounded chunks, **oldest-first**, advancing the watermark transactionally per batch (each batch commit is atomic per C7 — `memory_text` replacement + watermark advance together; a failed batch leaves the prior committed batch intact and the sequence resumable).

- Suggested bound: ~20–30k tokens of transcript per call (tunable; not load-bearing).
- **A full redistill (from null watermark over long history) is NOT a separate codepath.** It is the normal incremental distill — `(current doc, next oldest slice) → rewritten doc` — run as a loop until the watermark reaches the newest surviving message. Do not build a distinct "batch merge" path; reuse the incremental one. (This keeps reconsolidation behavior identical between incremental and full rebuild, and avoids a drift vector.)
- This requirement exists because full redistill now fires on a **normal user action** (delete — see slice 5), not a rare one. It cannot be a single call that overflows context or blocks the UI.

**S4-c. Distiller model default: opus, configurable.**
`[memory]` config gains `distiller_provider` + `distiller_model` (as planned).
Default `anthropic / claude-opus-4-8`. Rationale is on the merits, not
convenience: distillation is judge-salience + merge-against-prior-state +
honor-negative-constraints, and its errors **compound** (each doc is the next
distill's input). Small-model infidelities accrete rather than average out; this
is the wrong stage to put a noisy component. Keep the model configurable, but do
not treat Haiku-class output as an expected viable path for this memory layer.

---

## Slice 5 (delete propagation) amendments

**S5-a. Delete means renounce. Auto, no modal.**
User invariant: a deleted conversation is one whose content should leave *no trace* — not in transcript, not in memory, retroactively. This is stronger and cleaner than the planned `needs_redistill` flag, and it removes the stale-injection decision entirely (there is no "inject stale anyway" option, because it would never be wanted).

Replace the flag-and-defer approach with auto renounce-and-rebuild on `delete_conversation`:

1. Identify the buddy.
2. Determine watermark intersection: does the deleted conversation contain any message **at or before** the buddy's watermark under the total order (S1-a)?
3. **Clean case** — entire conversation strictly newer than watermark (never distilled, no residue in the doc): just delete the conversation. No redistill. The doc is already clean.
4. **Metabolized case** — any message at/before the watermark (already integrated into `memory_text`): the doc may contain renounced content, which a watermark reset alone does **not** remove. So:
   - reset the buddy watermark to null,
   - enter **injection suppression** for that buddy immediately (treat as cold-start — inject nothing — per the S1-b predicate),
   - kick off a **background batched redistill** (S4-b) from surviving buddy history,
   - replace the doc atomically when the rebuild completes, then lift suppression.

The renounced facts vanish because they are simply absent from the rebuild input. Injection suppression closes the async-gap leak: between delete and rebuild-complete, the buddy starts fresh rather than injecting a doc still containing renounced content. Starting fresh is strictly safer than injecting known-stale; it is the privacy-correct failure mode and falls out of the predicate already needed for cold start.

**S5-b. Scope honesty (no action, document only).**
Renunciation reaches the doc and the transcript, not Anthropic's prompt cache. If the deleted conversation's prefix is still warm (5m/1h TTL), that content persists in Anthropic infrastructure until the TTL bleeds out — out of the app's reach. Not worth chasing for a single-user client; note it in the delete-path comment so the boundary of "delete" is documented, not silently overclaimed.

---

## Test additions

- Watermark total-order determinism: interleaved-conversation fixture, assert `messages_newer_than_watermark_for_buddy` returns a stable, reproducible slice regardless of row insertion order (S1-a).
- Empty-doc / disabled / suppressed injection: assert the assembly layer injects nothing (no heading) for each of the four suppression conditions (S1-b).
- Cache-column NULL vs 0: OpenAI-compat row is NULL across cache classes; Anthropic uncached row is 0 (S1-c).
- Batched full-redistill: long-history fixture, assert it completes as a resumable sequence of bounded calls and produces the same doc as an unbounded distill would (codepath-identity check) (S4-b).
- Watermark-guarded no-op trigger: switch/quit with no new messages fires zero API calls (S4-a).
- Delete clean case: deleting an undistilled conversation triggers no redistill and leaves the doc byte-identical (S5-a, case 3).
- Delete metabolized case: deleting a distilled conversation suppresses injection, rebuilds from surviving history, and the rebuilt doc contains no token from the deleted conversation (S5-a, case 4).

---

*The doorstep keeps only what survives. Delete is renunciation; the rebuild is the doorstep forgetting on purpose.*
