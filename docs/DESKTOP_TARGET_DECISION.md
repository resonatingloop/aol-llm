# Desktop Target Decision

This note records the post-MVP desktop target decision for aol-llm.

## Decision

Keep Textual as the active app shell for the next iteration.

Reassess after the Textual app has a cleaner internal UI structure and enough
daily use to show where the terminal interface actually gets in the way.

## Why Textual Stays

Textual is already working for the core workflow: conversation list,
transcript, composer, model switching, retry, export, streaming output, and
token/cost status. The app is keyboard-first, local-first, and intended for one
Linux desktop user before it is anything broader.

The next useful work is not a toolkit rewrite. It is factoring the existing TUI
so the app state, chat orchestration, widgets, and modal flows are easier to
change without turning `ui/app.py` into the whole application.

## Options Compared

| Target | Implementation Cost | Packaging Friction | UI Quality | Linux Integration | Workflow Fit |
| --- | --- | --- | --- | --- | --- |
| Textual | Lowest. Current app already runs here. | Low for `uv` users; desktop launcher packaging still future work. | Good for keyboard chat, status, lists, and streaming text. Limited for rich native controls. | Terminal-native, reliable on Linux, but not a full desktop app experience. | Best current fit for fast iteration and keyboard-heavy use. |
| PySide6 | Medium to high. Requires rebuilding the shell and event flow. | Medium. Python GUI packaging needs more care than the current TUI. | Strong native-feeling widgets and layout control. | Good Linux desktop fit when packaged correctly. | Good future candidate if the app needs true desktop affordances. |
| Tauri 2 | Highest. Requires a web frontend plus a Python/Rust boundary decision. | Medium to high. Produces a desktop-shaped app, but adds build-system complexity. | Strong visual polish and modern UI potential. | Good if packaged well, but heavier than the current need. | Attractive later if the product becomes more GUI than terminal workflow. |

## Near-Term Direction

- Continue with Textual for the next iteration.
- Factor TUI code along existing boundaries before adding larger features.
- Keep provider, storage, config, and export contracts independent of Textual.
- Do not add PySide6, Tauri, or packaging-specific dependencies yet.

## Reassessment Trigger

Reopen this decision when at least one of these becomes true:

- The Textual UI blocks a high-frequency workflow that cannot be fixed cleanly.
- The app needs native desktop features such as file pickers, tray behavior,
  richer text editing, or better clipboard/window integration.
- Public installation needs a bundled desktop app rather than `uv run aol-llm`.
- The TUI factoring is done and the remaining friction is clearly toolkit-level.
