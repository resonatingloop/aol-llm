from pathlib import Path

import pytest

from aol_llm import config as config_module
from aol_llm.config import AppConfig, ProviderSettings, UIConfig


def test_load_config_returns_defaults_when_file_is_missing(tmp_path: Path) -> None:
    loaded = config_module.load_config(tmp_path / "missing.toml")

    assert loaded.ui.default_provider == "anthropic"
    assert loaded.ui.assistant_name == "assistant"
    assert loaded.providers["anthropic"].default_model == "claude-opus-4-8"
    assert loaded.providers["openai"].base_url == "https://api.openai.com/v1"


def test_save_and_load_config_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = AppConfig(
        ui=UIConfig(
            theme="dark",
            default_provider="openai",
            assistant_name="THRESHOLD36",
        ),
        providers={
            "anthropic": ProviderSettings(default_model="claude-sonnet-test"),
            "openai": ProviderSettings(
                default_model="gpt-test",
                base_url="https://api.openai.test/v1",
            ),
        },
    )

    config_module.save_config(original, path)
    loaded = config_module.load_config(path)

    assert loaded == original
    assert "api_key" not in path.read_text(encoding="utf-8")


def test_xdg_paths_use_platformdirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr(
        "aol_llm.config.platformdirs.user_config_dir", lambda appname: str(config_dir)
    )
    monkeypatch.setattr(
        "aol_llm.config.platformdirs.user_data_dir", lambda appname: str(data_dir)
    )

    assert config_module.config_path() == config_dir / "config.toml"
    assert config_module.database_path() == data_dir / "aol-llm.db"


def test_provider_settings_resolves_configured_provider() -> None:
    settings = config_module.provider_settings(config_module.default_config(), "openai")

    assert settings.default_model == "gpt-5"


def test_provider_settings_rejects_unknown_provider() -> None:
    with pytest.raises(KeyError, match="unknown provider config"):
        config_module.provider_settings(config_module.default_config(), "missing")
