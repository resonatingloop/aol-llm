"""Application config paths and TOML persistence."""

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Any

import platformdirs

APP_NAME = "aol-llm"
CONFIG_FILENAME = "config.toml"
DB_FILENAME = "aol-llm.db"


@dataclass(frozen=True)
class UIConfig:
    theme: str = "default"
    default_provider: str = "anthropic"
    assistant_name: str = "assistant"


@dataclass(frozen=True)
class ProviderSettings:
    default_model: str
    base_url: str | None = None


@dataclass(frozen=True)
class AppConfig:
    ui: UIConfig = field(default_factory=UIConfig)
    providers: dict[str, ProviderSettings] = field(default_factory=dict)


def user_config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME))


def user_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


def config_path() -> Path:
    return user_config_dir() / CONFIG_FILENAME


def database_path() -> Path:
    return user_data_dir() / DB_FILENAME


def default_config() -> AppConfig:
    return AppConfig(
        providers={
            "anthropic": ProviderSettings(default_model="claude-opus-4-7"),
            "openai": ProviderSettings(
                default_model="gpt-5",
                base_url="https://api.openai.com/v1",
            ),
        }
    )


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return default_config()

    data = tomllib.loads(target.read_text(encoding="utf-8"))
    return _parse_config(data)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_format_config(config), encoding="utf-8")


def provider_settings(config: AppConfig, provider_id: str) -> ProviderSettings:
    try:
        return config.providers[provider_id]
    except KeyError as error:
        raise KeyError(f"unknown provider config: {provider_id}") from error


def _parse_config(data: dict[str, Any]) -> AppConfig:
    ui_data = _dict_value(data, "ui")
    providers_data = _dict_value(data, "providers")
    return AppConfig(
        ui=UIConfig(
            theme=_str_value(ui_data, "theme", "default"),
            default_provider=_str_value(ui_data, "default_provider", "anthropic"),
            assistant_name=_str_value(ui_data, "assistant_name", "assistant"),
        ),
        providers={
            provider_id: _parse_provider_settings(provider_data)
            for provider_id, provider_data in providers_data.items()
            if isinstance(provider_id, str) and isinstance(provider_data, dict)
        },
    )


def _parse_provider_settings(data: dict[str, Any]) -> ProviderSettings:
    return ProviderSettings(
        default_model=_str_value(data, "default_model", ""),
        base_url=_optional_str_value(data, "base_url"),
    )


def _dict_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _str_value(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def _optional_str_value(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _format_config(config: AppConfig) -> str:
    lines = [
        "[ui]",
        f'theme = "{_toml_escape(config.ui.theme)}"',
        f'default_provider = "{_toml_escape(config.ui.default_provider)}"',
        f'assistant_name = "{_toml_escape(config.ui.assistant_name)}"',
        "",
    ]
    for provider_id in sorted(config.providers):
        settings = config.providers[provider_id]
        lines.extend(
            [
                f"[providers.{provider_id}]",
                f'default_model = "{_toml_escape(settings.default_model)}"',
            ]
        )
        if settings.base_url is not None:
            lines.append(f'base_url = "{_toml_escape(settings.base_url)}"')
        lines.append("")
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
