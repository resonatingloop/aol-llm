import pytest

from aol_llm import secrets


def test_keyring_service_uses_stable_provider_namespace() -> None:
    assert secrets.keyring_service("anthropic") == "aol-llm.anthropic"


def test_get_and_set_api_key_use_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_set_password(service: str, username: str, password: str) -> None:
        calls.append((service, username, password))

    def fake_get_password(service: str, username: str) -> str | None:
        assert service == "aol-llm.anthropic"
        assert username == "api_key"
        return "secret"

    monkeypatch.setattr("aol_llm.secrets.keyring.set_password", fake_set_password)
    monkeypatch.setattr("aol_llm.secrets.keyring.get_password", fake_get_password)

    secrets.set_api_key("anthropic", "secret")

    assert calls == [("aol-llm.anthropic", "api_key", "secret")]
    assert secrets.get_api_key("anthropic") == "secret"


def test_require_api_key_raises_actionable_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aol_llm.secrets.keyring.get_password", lambda service, username: None
    )

    with pytest.raises(
        secrets.MissingApiKeyError, match="missing API key for provider"
    ):
        secrets.require_api_key("anthropic")


def test_delete_api_key_uses_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_delete_password(service: str, username: str) -> None:
        calls.append((service, username))

    monkeypatch.setattr("aol_llm.secrets.keyring.delete_password", fake_delete_password)

    secrets.delete_api_key("openai")

    assert calls == [("aol-llm.openai", "api_key")]
