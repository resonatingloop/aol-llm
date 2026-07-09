# AIM — Memory Distiller Prompt: Authoring Brief

**Document purpose:** Codex's task is to write the actual distiller prompt artifact (`src/aol_llm/data/memory_distiller_prompt.md`, per the implementation plan — package data, versioned in git, no config override in v1). This brief specifies the prompt's required anatomy, content, and constraints. The prompt is a component with a hard contract, not creative writing: it will run unattended, per-batch, many times, and its output feeds its own next input. Design decisions below are settled; do not relitigate. Where judgment is needed, prefer the more conservative/explicit option and flag it.

**Canonical output shape:** `claude-memory-structure.md` (the seeded memory doc skeleton) is the authoritative structure the distiller must emit and maintain. The prompt's output contract points at that structure. Do not invent alternative sections.

---

## 1. What the prompt is

A pure function specified in English: `(current memory document, transcript slice) → rewritten memory document`. Called by the distiller job runner (slice 5 of the implementation plan), per batch, oldest-first, watermark-advanced. The same prompt must serve both an incremental pass over one conversation's slice and a full rebuild from null watermark (which is the same operation looped — codepath identity per amendment S4-b).

The prompt receives a **mode flag** from the job runner: `incremental` (default) or `refactor`. The runner decides when refactor fires (size threshold ~3k tokens, every-N-distills, or manual command — runner logic, not prompt logic). The prompt must define both behaviors.

---

## 2. Required prompt anatomy, in this order

Order is load-bearing: models weight early instructions heavily and launch generation from the end. Do not reorder.

1. **Role + channel purpose.** 2–3 sentences. This distiller serves a generative-conversation space spanning technical, philosophical, and esoteric registers. It holds what makes future conversations pull, at whatever register a thread lives in. It does not optimize for deliverables or task-state unless the transcript shows explicit task work.
2. **Inputs, explicitly named.** (1) the current memory document (possibly the seeded skeleton, possibly empty sections), (2) a transcript slice of new conversation, (3) the mode flag. Name them as distinct objects so later instructions can reference them precisely.
3. **Task + core invariant.** Produce a complete rewritten memory document integrating the slice into the current doc. **Rewrite in place; never append-only.** Superseded facts are replaced, not accumulated ("was deciding X vs Y" becomes "chose X because Z" — one fact, not two).
4. **Procedure** — the bulk. Written as a decision procedure with imperatives and branches, NOT as descriptive principles. The model must be able to execute it item-by-item. Content in §3 below.
5. **Output contract.** Emit the full document in the canonical structure: exact section order (Constants → Interpersonal → Threads), the italic descriptor lines preserved verbatim (they are sorting instructions, not decoration), monosemous tag grammar (`[hot]`/`[cooling]`/`[cold]` mean thread-warmth only, nowhere else), HTML comments preserved. Output the document and nothing else — no preamble, no commentary, no "here is the updated memory." Stray output is a return-value bug.
6. **Negative constraints** — gathered in one block late in the prompt (recency position). Content in §4.
7. **Worked example** — one full (current doc excerpt + slice excerpt → rewritten excerpt) demonstration. Requirements in §5. This section teaches more than the procedure; invest accordingly.

Use hard delimiters for runtime inputs: `<current_memory>`, `<transcript_slice>`, `<mode>`. The prompt text must make the instruction/data boundary unambiguous — the model must never read transcript content as instructions.

---

## 3. Procedure content (the rules the prompt must encode as executable steps)

### 3.1 Classification (first move, per item of new information)
Every fact extracted from the slice is classified as **constant**, **interpersonal**, or **thread** before anything else:
- **Constant**: durable identity, named frameworks, operating patterns, intellectual influences. Test per subsection: Purpose = what maria wants from the space; Context = durable fact about who she is; Concepts = a named idea of hers; Approach = interaction mechanics; Influences = metabolized intellectual diet.
- **Interpersonal**: a person, relationship, or situation with relational weight. Sub-classify: **Bond** (stable, near-static) or **Arc** (has a trajectory).
- **Thread**: active work — projects and tools on the warmth gradient.

### 3.2 Constants handling
- Near-permanent; do not cool from disuse.
- **Preserve Maria's phrasing verbatim.** Paraphrase is the failure mode: a paraphrased framework is a corrupted framework. When a constant is restated in the slice with refined wording, the refined version (hers) replaces the old; the distiller never "improves" wording itself.
- New constants enter only on strong evidence (explicitly framed as durable by Maria, or a framework she names). Default for new material is thread, not constant.

### 3.3 Interpersonal handling (inverted physics — anti-compression)
- The trajectory IS the content. Arcs keep their phase structure (phase → phase → phase) even as within-phase detail thins. Compress within a phase; never flatten the arc.
- **Handling notes in parentheses are directives.** Preserve them verbatim through every rewrite. Never remove or soften one. New entries touching charged material get a conservative default handling note flagged for Maria's review.
- An arc compresses toward a Bond only when genuinely settled across multiple slices — never proactively.
- No inferred narrative: record what the transcript states about a relationship, never a story constructed from adjacent facts.

### 3.4 Threads handling (the gradient + mandatory demotion)
- Per existing thread, per pass: **was it touched in this slice?** Touched → promote to `[hot]` / hold `[hot]`, update its line. Untouched → **demote one tier, no exceptions.** ("Might come back" is not an exception — if it comes back, one mention re-heats it.)
- Resolution follows warmth: `[hot]` holds nucleus + active state; `[cooling]` compresses to nucleus (description/purpose/philosophy, sheds implementation detail); `[cold]` is one recognizable line.
- New work mentioned in the slice enters `[hot]` with a one-line blurb.
- Two cold exits: a thread whose *solution* proved durable graduates its residue up into Constants (solved-to-constant — guard: only after the solution holds uncontradicted across later slices, never same-pass as the solve); a thread Maria explicitly says she's stopped compresses to a one-line `[cold]` tombstone **with a handling note** ("tried, not worth it — don't re-propose") or drops entirely if remembering it has no value. The distiller judges which; when unsure, tombstone.

### 3.5 Compression rule (applies everywhere except Interpersonal arcs)
**Compress by half-life, not by specificity.** The test per fact: "will this still be true in six months?" Durable specifics (a named framework, a physical fact, a signature item, a principle's mechanism) stay at full resolution. Volatile specifics (version numbers, current bug lists, pending micro-decisions, prices) compress to their durable nucleus or drop. Concreteness is NOT importance; specificity is NOT volatility. The prompt must state this explicitly because conflating them is the model's default error.

### 3.6 Learnings shape
Durable lessons are recorded as **principle + anchor**: the principle at transferable altitude, plus the single specific instance that precipitated it, kept as etiology ("compress by half-life, not specificity — e.g. kibbe type is specific AND durable; version numbers are specific AND volatile"). Anchor is one clause, not a paragraph. A principle without its anchor decays into a slogan; an anchor without its principle is trivia.

### 3.7 Mode behavior
- **incremental** (default): integrate the slice into the current doc with minimal restructuring. Touch what the slice touches plus mandatory demotions. Do not reorganize untouched sections.
- **refactor**: full-document pass. Additionally required: deduplicate (same fact in two homes → one home), consolidate keystones (scattered facts sharing a causal root gather into keystone-plus-consequences shape), verify every thread's tier against its actual last reinforcement, verify constants still read as Maria's phrasing, shed anything whose retention can't be justified. Refactor may restructure within sections but never alter the section skeleton itself.

### 3.8 Shed bias (the bloat spine — must be stated in these terms)
The document has a target mass (~2–3k tokens; this is a gauge, not a wall). **Holding material at full resolution is a cost that must be justified; the default for anything unreinforced is to compress or drop.** Shedding is the job done well, not information lost. The burden of proof is on keeping. This framing must appear explicitly — it exists to counteract the model's native preservationism, which is the primary cause of unbounded doc growth.

---

## 4. Negative constraints (one block, late position)

- No first person as the buddy; the doc is written in third person about Maria and the space — a stele, not a diary.
- No characterization, praise, or affect labels ("strong instincts," "friendly," "enjoys exploring") — identity facts yes, performance review no. Opinionated framing about *ideas* is permitted; assessment of *Maria as a performer* is banned.
- No inferring connective narrative between facts that happen to sit adjacent — a fact carries only what it states. (Two unrelated "recovery" threads do not make a recovery arc.)
- No paraphrasing Constants or handling notes — preserve wording exactly.
- No promoting a live thread to a settled constant in the same pass it appears resolved; "resolved" must survive later slices uncontradicted first.
- No time-relative language anywhere ("recently," "last week," "currently deciding") — warmth tags carry recency; prose must be true whenever read.
- No new sections, no removed descriptors, no repurposed tags.
- Output only the document.

## 5. Worked example requirements

One rich example, not several thin ones. It must demonstrate, in a single before/after:
1. A constant held verbatim while surrounding material changes (correct), contrasted with the canonical failure: "suspend belief and disbelief" paraphrased into "suspend-and-disbelieve" — shown as WRONG with a one-line why (paraphrase silently replaced her epistemics with a plausible neighbor).
2. A durable specific kept at full resolution under compression pressure.
3. A volatile specific compressed to nucleus ("v0.5, three open bugs, pricing pending" → "her first public repo, a threshold-themed LLM messaging client").
4. A thread demoted for non-reinforcement, its line compressing to match the new tier.
5. An arc updated by appending a phase, trajectory intact, handling note preserved.
6. Superseded-fact replacement (was-deciding → chose-because).

Build the example on fictional-but-plausible content in the canonical structure — do NOT copy Maria's real seeded doc into the prompt (the real doc arrives at runtime as `<current_memory>`; duplicating it in the prompt creates two divergent sources of truth).

## 6. Acceptance checks (for the three-way model diff Maria will run)

The prompt is testable against four named failure modes; a good prompt makes these detectable in output:
- **Hoarding**: doc grows pass-over-pass without demotions → shed-bias or mandatory-demotion language too weak.
- **Arc-flattening**: interpersonal trajectory collapsed to a status → anti-compression section failed.
- **Constant-paraphrase**: framework wording altered → verbatim rule failed.
- **Half-life misjudgment**: version numbers held hot / durable specifics dropped → §3.5 failed.

Deliverable: the prompt file, plus a short note listing any places where you chose between plausible readings of this brief.
