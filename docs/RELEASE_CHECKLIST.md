# Release Checklist

This checklist tracks the first public GitHub-ready iteration of aol-llm.

## Current Release State

- [x] Project brief and contracts are written.
- [x] Python package metadata exists in `pyproject.toml`.
- [x] `aol-llm` console script launches the app.
- [x] MIT license is present.
- [x] README includes install, run, configuration, development, and project-doc
  links.
- [x] User manual covers setup, API keys, keybindings, exports, local files, and
  basic troubleshooting.
- [x] GitHub Actions runs pytest, ruff, formatting checks, and strict mypy.
- [x] Textual MVP supports local conversations, streaming providers, model
  switching, retry, archive/delete, a-way messages, and export.
- [x] Desktop target has been reassessed after the MVP.

## Before Tagging A Public Release

- [ ] Capture a screenshot or short terminal recording for the README.
- [ ] Run the full check suite from a clean checkout.
- [ ] Confirm the documented Anthropic and OpenAI-compatible setup still matches
  the current app behavior.
- [ ] Decide whether to publish built artifacts or keep the first release
  source-only.
- [ ] Verify no local databases, exports, API keys, or scratch files are staged.
- [ ] Tag the release only after the README status matches the shipped behavior.

## Release Commands

```bash
uv sync --locked
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy --strict src tests
uv build
```

`dist/` is ignored by git. Build artifacts should be attached to a GitHub
release only if the release is meant to include packaged source/wheel files.
