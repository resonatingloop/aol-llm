from datetime import UTC, datetime

from aol_llm.core.types import BuddyMemory
from aol_llm.prompt_assembly import (
    MEMORY_BLOCK_HEADING,
    assemble_prompt,
    should_inject_memory,
)


def buddy_memory(
    memory_text: str = "Maria and this buddy are working on prompt caching.",
    enabled: bool = True,
    suppress_injection: bool = False,
) -> BuddyMemory:
    return BuddyMemory(
        buddy_id="buddy-id",
        memory_text=memory_text,
        enabled=enabled,
        suppress_injection=suppress_injection,
        watermark_created_at=None,
        watermark_message_id=None,
        updated_at=datetime.now(UTC),
    )


def test_no_memory_row_injects_no_memory_block() -> None:
    assembled = assemble_prompt("Be concise.", None)

    assert assembled.system_blocks == ("Be concise.",)
    assert assembled.system_text == "Be concise."
    system_text = assembled.system_text
    assert system_text is not None
    assert MEMORY_BLOCK_HEADING not in system_text
    assert should_inject_memory(None) is False


def test_disabled_memory_row_injects_nothing() -> None:
    memory = buddy_memory(enabled=False)
    assembled = assemble_prompt("Be concise.", memory)

    assert assembled.system_blocks == ("Be concise.",)
    system_text = assembled.system_text
    assert system_text is not None
    assert MEMORY_BLOCK_HEADING not in system_text
    assert should_inject_memory(memory) is False


def test_empty_memory_row_injects_nothing() -> None:
    memory = buddy_memory(memory_text="  \n ")
    assembled = assemble_prompt("Be concise.", memory)

    assert assembled.system_blocks == ("Be concise.",)
    system_text = assembled.system_text
    assert system_text is not None
    assert MEMORY_BLOCK_HEADING not in system_text
    assert should_inject_memory(memory) is False


def test_suppressed_memory_row_injects_nothing() -> None:
    memory = buddy_memory(suppress_injection=True)
    assembled = assemble_prompt("Be concise.", memory)

    assert assembled.system_blocks == ("Be concise.",)
    system_text = assembled.system_text
    assert system_text is not None
    assert MEMORY_BLOCK_HEADING not in system_text
    assert should_inject_memory(memory) is False


def test_positive_memory_row_injects_memory_block_after_away_message() -> None:
    memory = buddy_memory(memory_text=" Standing decision. ")
    assembled = assemble_prompt("Be concise.", memory)

    assert len(assembled.system_blocks) == 2
    assert assembled.system_blocks[0] == "Be concise."
    assert assembled.system_blocks[1].startswith(MEMORY_BLOCK_HEADING)
    assert "Standing decision." in assembled.system_blocks[1]
    assert should_inject_memory(memory) is True


def test_memory_block_can_be_the_only_system_block() -> None:
    assembled = assemble_prompt(None, buddy_memory())

    assert len(assembled.system_blocks) == 1
    assert assembled.system_blocks[0].startswith(MEMORY_BLOCK_HEADING)


def test_openai_compatible_system_text_is_plain_flattened_prefix() -> None:
    assembled = assemble_prompt("Be concise.", buddy_memory("Remember the atlas work."))

    assert assembled.system_text == "\n\n".join(assembled.system_blocks)
    assert assembled.system_text is not None
    assert assembled.system_text.index("Be concise.") < assembled.system_text.index(
        MEMORY_BLOCK_HEADING
    )


def test_empty_prefix_serializes_to_none() -> None:
    assembled = assemble_prompt("", None)

    assert assembled.system_blocks == ()
    assert assembled.system_text is None


def test_serialized_system_prefix_is_stable_across_turns() -> None:
    memory = buddy_memory("Stable fact.")

    first = assemble_prompt("Be concise.", memory)
    second = assemble_prompt("Be concise.", memory)

    assert first == second
    assert first.system_text == second.system_text
