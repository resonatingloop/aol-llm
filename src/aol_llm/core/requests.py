"""Provider-neutral request normalization."""

from dataclasses import dataclass
from typing import Sequence

from aol_llm.core.types import Message

DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_TEMPERATURE = 1.0


@dataclass(frozen=True)
class NormalizedChatRequest:
    messages: tuple[Message, ...]
    system: str | None
    model: str
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    temperature: float = DEFAULT_TEMPERATURE


def normalize_chat_request(
    messages: Sequence[Message],
    system: str | None,
    model: str,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> NormalizedChatRequest:
    """Freeze request inputs without folding system text into messages."""

    return NormalizedChatRequest(
        messages=tuple(messages),
        system=system,
        model=model,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
