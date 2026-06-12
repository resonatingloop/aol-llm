from dataclasses import fields, is_dataclass
from pathlib import Path

from aol_llm.chat import DEFAULT_PROVIDER_MODELS
from aol_llm.config import default_config
from aol_llm.core.pricing import load_pricing_snapshot
from aol_llm.core import types
from aol_llm.ui.styles import APP_BINDINGS
from textual.binding import Binding


ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "README.md": ROOT / "README.md",
    "docs/USER_MANUAL.md": ROOT / "docs" / "USER_MANUAL.md",
    "CONTRACTS.md": ROOT / "CONTRACTS.md",
    "docs/CODEBASE_SCHEMA.md": ROOT / "docs" / "CODEBASE_SCHEMA.md",
}


def read_doc(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return text.lower().replace("_", " ")


def binding_rows() -> list[tuple[str, str]]:
    return [
        (binding.key, binding.description)
        for binding in APP_BINDINGS
        if isinstance(binding, Binding)
    ]


def built_in_models() -> set[str]:
    models: set[str] = set()
    for provider_id, settings in default_config().providers.items():
        models.add(settings.default_model)
        models.update(DEFAULT_PROVIDER_MODELS.get(provider_id, ()))
    return models


def test_documented_keybindings_match_app_bindings() -> None:
    for doc_name, path in DOCS.items():
        content = normalized(read_doc(path))
        for key, description in binding_rows():
            assert key in content, f"{doc_name} missing keybinding {key}"
            assert description.lower() in content, (
                f"{doc_name} missing keybinding label {description}"
            )


def test_documented_default_providers_match_config() -> None:
    providers = default_config().providers
    for doc_name, path in DOCS.items():
        content = read_doc(path)
        for provider_id, settings in providers.items():
            assert provider_id in content, f"{doc_name} missing provider {provider_id}"
            assert settings.default_model in content, (
                f"{doc_name} missing default model {settings.default_model}"
            )
            if settings.base_url is not None:
                assert settings.base_url in content, (
                    f"{doc_name} missing base URL {settings.base_url}"
                )


def test_documented_keyring_services_match_builtin_providers() -> None:
    providers = default_config().providers
    for doc_name, path in DOCS.items():
        content = read_doc(path)
        for provider_id in providers:
            service = f"aol-llm.{provider_id}"
            assert service in content, f"{doc_name} missing keyring service {service}"


def test_documented_migrations_match_migration_files() -> None:
    migration_stems = {
        path.stem for path in (ROOT / "src/aol_llm/storage/migrations").glob("*.sql")
    }
    for doc_name in ("CONTRACTS.md", "docs/CODEBASE_SCHEMA.md"):
        content = read_doc(DOCS[doc_name])
        for stem in migration_stems:
            assert stem in content, f"{doc_name} missing migration {stem}"


def test_contracts_canonical_dataclasses_match_core_types() -> None:
    content = read_doc(DOCS["CONTRACTS.md"])
    for name in (
        "Message",
        "Conversation",
        "Buddy",
        "Prompt",
        "PromptVersion",
        "ProviderConfig",
        "PromptCacheControl",
        "TokenUsage",
        "StreamChunk",
    ):
        cls = getattr(types, name)
        assert is_dataclass(cls)
        assert f"class {name}" in content
        for field in fields(cls):
            assert field.name in content, f"CONTRACTS.md missing {name}.{field.name}"


def test_codebase_schema_mentions_src_modules() -> None:
    content = read_doc(DOCS["docs/CODEBASE_SCHEMA.md"])
    ignored_names = {"__init__.py", "__main__.py"}
    for path in (ROOT / "src/aol_llm").rglob("*.py"):
        if path.name in ignored_names:
            continue
        relative = path.relative_to(ROOT).as_posix()
        assert relative in content, f"CODEBASE_SCHEMA.md missing {relative}"


def test_validation_commands_are_documented() -> None:
    commands = (
        "uv run pytest",
        "uv run ruff check",
        "uv run ruff format --check",
        "uv run mypy --strict src tests",
    )
    for doc_name in ("README.md", "CONTRACTS.md", "docs/CODEBASE_SCHEMA.md"):
        content = read_doc(DOCS[doc_name])
        for command in commands:
            assert command in content, (
                f"{doc_name} missing validation command {command}"
            )


def test_pricing_snapshot_covers_builtin_models() -> None:
    snapshot = load_pricing_snapshot()
    for model in built_in_models():
        assert model in snapshot, f"pricing snapshot missing {model}"
        entry = snapshot[model]
        if entry.get("priced") is True:
            assert isinstance(entry.get("input_per_mtok"), int | float)
            assert isinstance(entry.get("output_per_mtok"), int | float)
        else:
            assert entry.get("priced") is False
            assert isinstance(entry.get("reason"), str)


def test_docs_describe_pricing_snapshot_contract() -> None:
    required_phrases = (
        "src/aol_llm/data/model_prices.json",
        "scripts/refresh_pricing.py",
        "missing_from_litellm_snapshot",
    )
    for doc_name in ("README.md", "CONTRACTS.md", "docs/CODEBASE_SCHEMA.md"):
        content = read_doc(DOCS[doc_name])
        for phrase in required_phrases:
            assert phrase in content, f"{doc_name} missing {phrase}"


def test_docs_do_not_contain_known_stale_claims() -> None:
    combined = "\n".join(read_doc(path) for path in DOCS.values()).lower()
    stale_phrases = (
        "ctrl+q",
        "ctrl+shift+c",
        "assistant display name",
        "gpt-5.5",
        "static rate card at `src/aol_llm/pricing.json`",
        "placeholder prices",
        '[providers.anthropic]\ndefault_model = "claude-opus-4-7"',
    )
    for phrase in stale_phrases:
        assert phrase not in combined
