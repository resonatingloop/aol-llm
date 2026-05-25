"""Keyring-backed provider secret access."""

import keyring

API_KEY_USERNAME = "api_key"


class MissingApiKeyError(RuntimeError):
    """Raised when a provider API key is required but not configured."""


def keyring_service(provider_id: str) -> str:
    return f"aol-llm.{provider_id}"


def get_api_key(provider_id: str) -> str | None:
    return keyring.get_password(keyring_service(provider_id), API_KEY_USERNAME)


def require_api_key(provider_id: str) -> str:
    api_key = get_api_key(provider_id)
    if api_key is None:
        raise MissingApiKeyError(f"missing API key for provider: {provider_id}")
    return api_key


def set_api_key(provider_id: str, api_key: str) -> None:
    keyring.set_password(keyring_service(provider_id), API_KEY_USERNAME, api_key)


def delete_api_key(provider_id: str) -> None:
    keyring.delete_password(keyring_service(provider_id), API_KEY_USERNAME)
