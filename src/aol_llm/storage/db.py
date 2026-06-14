"""SQLite repository functions."""

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import cast
from uuid import uuid4

from aol_llm.core.types import (
    Buddy,
    BuddyMemory,
    Conversation,
    Message,
    Prompt,
    PromptStatus,
    PromptVersion,
    ProviderConfig,
    Role,
)
from aol_llm.storage.connection import get_connection as _get_connection
from aol_llm.storage.connection import init_db as _init_db
from aol_llm.storage.rows import (
    buddy_from_row,
    buddy_memory_from_row,
    conversation_from_row,
    db_value,
    format_dt,
    message_from_row,
    prompt_from_row,
    prompt_version_from_row,
    provider_from_row,
)


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    return _get_connection(path)


def init_db(path: Path | None = None) -> None:
    _init_db(path)


def create_conversation(
    title: str,
    provider_id: str,
    model: str,
    system_prompt: str | None = None,
    buddy_id: str | None = None,
    prompt_version_id: str | None = None,
    assistant_name: str | None = None,
    path: Path | None = None,
) -> Conversation:
    now = _now()
    conversation = Conversation(
        id=uuid4().hex,
        title=title,
        system_prompt=system_prompt,
        provider_id=provider_id,
        model=model,
        created_at=now,
        updated_at=now,
        buddy_id=buddy_id,
        prompt_version_id=prompt_version_id,
        assistant_name=assistant_name,
    )
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO conversations
                (id, title, system_prompt, provider_id, model, buddy_id, prompt_version_id, assistant_name, created_at, updated_at, archived)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation.id,
                conversation.title,
                conversation.system_prompt,
                conversation.provider_id,
                conversation.model,
                conversation.buddy_id,
                conversation.prompt_version_id,
                conversation.assistant_name,
                format_dt(conversation.created_at),
                format_dt(conversation.updated_at),
                int(conversation.archived),
            ),
        )
    return conversation


def list_conversations(
    include_archived: bool = False,
    path: Path | None = None,
) -> list[Conversation]:
    sql = "SELECT * FROM conversations"
    params: tuple[int, ...] = ()
    if not include_archived:
        sql += " WHERE archived = ?"
        params = (0,)
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with get_connection(path) as connection:
        return [conversation_from_row(row) for row in connection.execute(sql, params)]


def list_conversations_for_buddy(
    buddy_id: str,
    include_archived: bool = False,
    path: Path | None = None,
) -> list[Conversation]:
    sql = "SELECT * FROM conversations WHERE buddy_id = ?"
    params: tuple[object, ...] = (buddy_id,)
    if not include_archived:
        sql += " AND archived = ?"
        params = (buddy_id, 0)
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with get_connection(path) as connection:
        return [conversation_from_row(row) for row in connection.execute(sql, params)]


def get_conversation(id: str, path: Path | None = None) -> Conversation:
    with get_connection(path) as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"unknown conversation: {id}")
    return conversation_from_row(row)


def update_conversation(
    id: str, path: Path | None = None, **fields: object
) -> Conversation:
    allowed = {
        "title",
        "system_prompt",
        "provider_id",
        "model",
        "buddy_id",
        "prompt_version_id",
        "assistant_name",
        "archived",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise KeyError(f"unknown conversation fields: {', '.join(sorted(unknown))}")
    if not fields:
        return get_conversation(id, path)

    updated = {**fields, "updated_at": format_dt(_now())}
    assignments = ", ".join(f"{field} = ?" for field in updated)
    values = [db_value(value) for value in updated.values()]
    values.append(id)
    with get_connection(path) as connection:
        connection.execute(
            f"UPDATE conversations SET {assignments} WHERE id = ?", values
        )
    return get_conversation(id, path)


def delete_conversation(id: str, path: Path | None = None) -> None:
    with get_connection(path) as connection:
        connection.execute("DELETE FROM conversations WHERE id = ?", (id,))


def add_message(
    conversation_id: str,
    role: Role,
    content: str,
    path: Path | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    prompt_version_id: str | None = None,
    cache_creation_5m_input_tokens: int | None = None,
    cache_creation_1h_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
) -> Message:
    message = Message(
        id=uuid4().hex,
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=_now(),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        prompt_version_id=prompt_version_id,
        cache_creation_5m_input_tokens=cache_creation_5m_input_tokens,
        cache_creation_1h_input_tokens=cache_creation_1h_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, model, input_tokens, output_tokens,
                 cost_usd, prompt_version_id, cache_creation_5m_input_tokens,
                 cache_creation_1h_input_tokens, cache_read_input_tokens, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.conversation_id,
                message.role,
                message.content,
                message.model,
                message.input_tokens,
                message.output_tokens,
                message.cost_usd,
                message.prompt_version_id,
                message.cache_creation_5m_input_tokens,
                message.cache_creation_1h_input_tokens,
                message.cache_read_input_tokens,
                format_dt(message.created_at),
            ),
        )
    return message


def list_messages(conversation_id: str, path: Path | None = None) -> list[Message]:
    with get_connection(path) as connection:
        rows = connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, id",
            (conversation_id,),
        )
        return [message_from_row(row) for row in rows]


def delete_message(id: str, path: Path | None = None) -> None:
    with get_connection(path) as connection:
        connection.execute("DELETE FROM messages WHERE id = ?", (id,))


def list_buddies(
    include_archived: bool = False,
    path: Path | None = None,
) -> list[Buddy]:
    sql = "SELECT * FROM buddies"
    params: tuple[int, ...] = ()
    if not include_archived:
        sql += " WHERE archived = ?"
        params = (0,)
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with get_connection(path) as connection:
        return [buddy_from_row(row) for row in connection.execute(sql, params)]


def get_buddy(id: str, path: Path | None = None) -> Buddy:
    with get_connection(path) as connection:
        row = connection.execute("SELECT * FROM buddies WHERE id = ?", (id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown buddy: {id}")
    return buddy_from_row(row)


def get_buddy_memory(buddy_id: str, path: Path | None = None) -> BuddyMemory | None:
    with get_connection(path) as connection:
        row = connection.execute(
            "SELECT * FROM buddy_memories WHERE buddy_id = ?",
            (buddy_id,),
        ).fetchone()
    return None if row is None else buddy_memory_from_row(row)


def upsert_buddy_memory(
    buddy_id: str,
    memory_text: str,
    path: Path | None = None,
    enabled: bool = True,
    suppress_injection: bool = False,
    watermark_created_at: str | None = None,
    watermark_message_id: str | None = None,
) -> BuddyMemory:
    now = format_dt(_now())
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO buddy_memories
                (buddy_id, memory_text, enabled, suppress_injection,
                 watermark_created_at, watermark_message_id, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(buddy_id) DO UPDATE SET
                memory_text = excluded.memory_text,
                enabled = excluded.enabled,
                suppress_injection = excluded.suppress_injection,
                watermark_created_at = excluded.watermark_created_at,
                watermark_message_id = excluded.watermark_message_id,
                updated_at = excluded.updated_at
            """,
            (
                buddy_id,
                memory_text,
                int(enabled),
                int(suppress_injection),
                watermark_created_at,
                watermark_message_id,
                now,
            ),
        )
    memory = get_buddy_memory(buddy_id, path)
    assert memory is not None
    return memory


def set_buddy_memory_enabled(
    buddy_id: str,
    enabled: bool,
    path: Path | None = None,
) -> BuddyMemory:
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO buddy_memories (buddy_id, updated_at, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(buddy_id) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (buddy_id, format_dt(_now()), int(enabled)),
        )
    memory = get_buddy_memory(buddy_id, path)
    assert memory is not None
    return memory


def set_buddy_memory_suppressed(
    buddy_id: str,
    suppressed: bool,
    path: Path | None = None,
) -> BuddyMemory:
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO buddy_memories
                (buddy_id, updated_at, suppress_injection)
            VALUES
                (?, ?, ?)
            ON CONFLICT(buddy_id) DO UPDATE SET
                suppress_injection = excluded.suppress_injection,
                updated_at = excluded.updated_at
            """,
            (buddy_id, format_dt(_now()), int(suppressed)),
        )
    memory = get_buddy_memory(buddy_id, path)
    assert memory is not None
    return memory


def clear_buddy_memory(buddy_id: str, path: Path | None = None) -> BuddyMemory:
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO buddy_memories
                (buddy_id, memory_text, suppress_injection, updated_at)
            VALUES
                (?, '', 0, ?)
            ON CONFLICT(buddy_id) DO UPDATE SET
                memory_text = '',
                suppress_injection = 0,
                watermark_created_at = NULL,
                watermark_message_id = NULL,
                updated_at = excluded.updated_at
            """,
            (buddy_id, format_dt(_now())),
        )
    memory = get_buddy_memory(buddy_id, path)
    assert memory is not None
    return memory


def messages_newer_than_watermark_for_buddy(
    buddy_id: str,
    path: Path | None = None,
) -> list[Message]:
    memory = get_buddy_memory(buddy_id, path)
    sql = """
        SELECT messages.*
        FROM messages
        JOIN conversations ON conversations.id = messages.conversation_id
        WHERE conversations.buddy_id = ?
    """
    params: list[object] = [buddy_id]
    if (
        memory is not None
        and memory.watermark_created_at is not None
        and memory.watermark_message_id is not None
    ):
        sql += """
          AND (
              messages.created_at > ?
              OR (
                  messages.created_at = ?
                  AND messages.id > ?
              )
          )
        """
        params.extend(
            [
                memory.watermark_created_at,
                memory.watermark_created_at,
                memory.watermark_message_id,
            ]
        )
    sql += " ORDER BY messages.created_at, messages.id"
    with get_connection(path) as connection:
        return [message_from_row(row) for row in connection.execute(sql, params)]


def update_buddy(id: str, path: Path | None = None, **fields: object) -> Buddy:
    allowed = {"name", "screen_name", "archived"}
    unknown = set(fields) - allowed
    if unknown:
        raise KeyError(f"unknown buddy fields: {', '.join(sorted(unknown))}")
    if not fields:
        return get_buddy(id, path)

    updated = {**fields, "updated_at": format_dt(_now())}
    assignments = ", ".join(f"{field} = ?" for field in updated)
    values = [db_value(value) for value in updated.values()]
    values.append(id)
    with get_connection(path) as connection:
        connection.execute(f"UPDATE buddies SET {assignments} WHERE id = ?", values)
    return get_buddy(id, path)


def buddy_exists(provider_id: str, model: str, path: Path | None = None) -> bool:
    with get_connection(path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM buddies
            WHERE provider_id = ? AND model = ?
            LIMIT 1
            """,
            (provider_id, model),
        ).fetchone()
    return row is not None


def ensure_buddy(provider_id: str, model: str, path: Path | None = None) -> Buddy:
    with get_connection(path) as connection:
        row = connection.execute(
            """
            SELECT * FROM buddies
            WHERE provider_id = ? AND model = ? AND archived = 0
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (provider_id, model),
        ).fetchone()
    if row is not None:
        return buddy_from_row(row)

    default_version = default_prompt_version(path)
    return create_buddy(
        name=f"{provider_id} / {model}",
        screen_name=f"{provider_id} / {model}",
        provider_id=provider_id,
        model=model,
        prompt_id=default_version.prompt_id,
        prompt_version_id=default_version.id,
        path=path,
    )


def create_buddy(
    name: str,
    screen_name: str,
    provider_id: str,
    model: str,
    prompt_id: str | None,
    prompt_version_id: str | None,
    path: Path | None = None,
) -> Buddy:
    now = _now()
    buddy = Buddy(
        id=uuid4().hex,
        name=name,
        screen_name=screen_name,
        provider_id=provider_id,
        model=model,
        prompt_id=prompt_id,
        prompt_version_id=prompt_version_id,
        created_at=now,
        updated_at=now,
    )
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO buddies
                (id, name, screen_name, provider_id, model, prompt_id, prompt_version_id, created_at, updated_at, archived)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                buddy.id,
                buddy.name,
                buddy.screen_name,
                buddy.provider_id,
                buddy.model,
                buddy.prompt_id,
                buddy.prompt_version_id,
                format_dt(buddy.created_at),
                format_dt(buddy.updated_at),
                int(buddy.archived),
            ),
        )
    return buddy


def create_prompt(
    name: str,
    gloss: str,
    core: str,
    path: Path | None = None,
    signature: str | None = None,
    default_provider: str | None = None,
    default_model: str | None = None,
    status: PromptStatus = "draft",
    doorwords: str | None = None,
    horizon_minutes: int | None = None,
    mischief_range: str | None = None,
    dismissal_protocol: str | None = None,
    ritual_twin_id: str | None = None,
    current_version_id: str | None = None,
) -> Prompt:
    now = _now()
    prompt = Prompt(
        id=uuid4().hex,
        name=name,
        gloss=gloss,
        core=core,
        signature=signature,
        default_provider=default_provider,
        default_model=default_model,
        status=status,
        doorwords=doorwords,
        horizon_minutes=horizon_minutes,
        mischief_range=mischief_range,
        dismissal_protocol=dismissal_protocol,
        ritual_twin_id=ritual_twin_id,
        current_version_id=current_version_id,
        created_at=now,
        updated_at=now,
    )
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO prompts
                (id, name, gloss, core, signature, default_provider, default_model,
                 status, doorwords, horizon_minutes, mischief_range,
                 dismissal_protocol, ritual_twin_id, current_version_id,
                 created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prompt.id,
                prompt.name,
                prompt.gloss,
                prompt.core,
                prompt.signature,
                prompt.default_provider,
                prompt.default_model,
                prompt.status,
                prompt.doorwords,
                prompt.horizon_minutes,
                prompt.mischief_range,
                prompt.dismissal_protocol,
                prompt.ritual_twin_id,
                prompt.current_version_id,
                format_dt(prompt.created_at),
                format_dt(prompt.updated_at),
            ),
        )
    return prompt


def list_prompts(
    status: PromptStatus | None = None,
    path: Path | None = None,
) -> list[Prompt]:
    sql = "SELECT * FROM prompts"
    params: tuple[str, ...] = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with get_connection(path) as connection:
        return [prompt_from_row(row) for row in connection.execute(sql, params)]


def get_prompt(id: str, path: Path | None = None) -> Prompt:
    with get_connection(path) as connection:
        row = connection.execute("SELECT * FROM prompts WHERE id = ?", (id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown prompt: {id}")
    return prompt_from_row(row)


def create_prompt_version(
    prompt: Prompt,
    path: Path | None = None,
    parent_version_id: str | None = None,
    note: str | None = None,
) -> PromptVersion:
    version = PromptVersion(
        id=uuid4().hex,
        prompt_id=prompt.id,
        parent_version_id=parent_version_id,
        name=prompt.name,
        gloss=prompt.gloss,
        core=prompt.core,
        signature=prompt.signature,
        default_provider=prompt.default_provider,
        default_model=prompt.default_model,
        status=prompt.status,
        doorwords=prompt.doorwords,
        horizon_minutes=prompt.horizon_minutes,
        mischief_range=prompt.mischief_range,
        dismissal_protocol=prompt.dismissal_protocol,
        ritual_twin_id=prompt.ritual_twin_id,
        note=note,
        created_at=_now(),
    )
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO prompt_versions
                (id, prompt_id, parent_version_id, name, gloss, core, signature,
                 default_provider, default_model, status, doorwords,
                 horizon_minutes, mischief_range, dismissal_protocol,
                 ritual_twin_id, note, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.id,
                version.prompt_id,
                version.parent_version_id,
                version.name,
                version.gloss,
                version.core,
                version.signature,
                version.default_provider,
                version.default_model,
                version.status,
                version.doorwords,
                version.horizon_minutes,
                version.mischief_range,
                version.dismissal_protocol,
                version.ritual_twin_id,
                version.note,
                format_dt(version.created_at),
            ),
        )
    return version


def get_prompt_version(id: str, path: Path | None = None) -> PromptVersion:
    with get_connection(path) as connection:
        row = connection.execute(
            "SELECT * FROM prompt_versions WHERE id = ?", (id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"unknown prompt version: {id}")
    return prompt_version_from_row(row)


def update_prompt_current_version(
    prompt_id: str,
    version_id: str,
    path: Path | None = None,
) -> Prompt:
    with get_connection(path) as connection:
        connection.execute(
            """
            UPDATE prompts
            SET current_version_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (version_id, format_dt(_now()), prompt_id),
        )
    return get_prompt(prompt_id, path)


def default_prompt_version(path: Path | None = None) -> PromptVersion:
    with get_connection(path) as connection:
        row = connection.execute(
            """
            SELECT prompt_versions.*
            FROM prompt_versions
            JOIN prompts ON prompts.current_version_id = prompt_versions.id
            WHERE prompts.name = 'Available'
            ORDER BY prompts.created_at
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        prompt = create_prompt(
            name="Available",
            gloss="ready to chat",
            core="",
            path=path,
            status="canonical",
        )
        version = create_prompt_version(
            prompt,
            path=path,
            note="seeded default a-way message",
        )
        update_prompt_current_version(prompt.id, version.id, path)
        return version
    return prompt_version_from_row(row)


def save_provider(config: ProviderConfig, path: Path | None = None) -> None:
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO providers
                (id, kind, display_name, base_url, keyring_service, default_model, available_models_json)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                display_name = excluded.display_name,
                base_url = excluded.base_url,
                keyring_service = excluded.keyring_service,
                default_model = excluded.default_model,
                available_models_json = excluded.available_models_json
            """,
            (
                config.id,
                config.kind,
                config.display_name,
                config.base_url,
                config.keyring_service,
                config.default_model,
                json.dumps(config.available_models),
            ),
        )


def list_providers(path: Path | None = None) -> list[ProviderConfig]:
    with get_connection(path) as connection:
        return [
            provider_from_row(row)
            for row in connection.execute("SELECT * FROM providers ORDER BY id")
        ]


def set_app_setting(key: str, value: str, path: Path | None = None) -> None:
    with get_connection(path) as connection:
        connection.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_app_setting(key: str, path: Path | None = None) -> str | None:
    with get_connection(path) as connection:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return None if row is None else cast(str, row["value"])


def _now() -> datetime:
    return datetime.now(UTC)
