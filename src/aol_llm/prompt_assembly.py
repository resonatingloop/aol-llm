"""Stable prompt prefix assembly."""

from dataclasses import dataclass

from aol_llm.core.types import BuddyMemory

MEMORY_BLOCK_HEADING = "## Memory of prior conversations"
MEMORY_BLOCK_DELIMITER = "---"


@dataclass(frozen=True)
class AssembledPrompt:
    system_blocks: tuple[str, ...]

    @property
    def system_text(self) -> str | None:
        if not self.system_blocks:
            return None
        return "\n\n".join(self.system_blocks)


def assemble_prompt(
    away_message: str | None,
    buddy_memory: BuddyMemory | None,
) -> AssembledPrompt:
    blocks: list[str] = []
    if away_message is not None and away_message.strip():
        blocks.append(away_message)

    if should_inject_memory(buddy_memory):
        assert buddy_memory is not None
        blocks.append(_memory_block(buddy_memory.memory_text))

    return AssembledPrompt(system_blocks=tuple(blocks))


def should_inject_memory(buddy_memory: BuddyMemory | None) -> bool:
    return (
        buddy_memory is not None
        and buddy_memory.enabled
        and bool(buddy_memory.memory_text.strip())
        and not buddy_memory.suppress_injection
    )


def _memory_block(memory_text: str) -> str:
    return (
        f"{MEMORY_BLOCK_HEADING}\n"
        f"{MEMORY_BLOCK_DELIMITER}\n"
        f"{memory_text.strip()}\n"
        f"{MEMORY_BLOCK_DELIMITER}"
    )
