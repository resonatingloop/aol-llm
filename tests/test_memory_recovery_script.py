from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys

from aol_llm.storage import db

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "baseline_memory_backlog.py"


def test_recovery_script_dry_run_then_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    backup_path = tmp_path / "private" / "before-baseline.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-a", db_path)
    conversation = db.create_conversation(
        "Chat",
        "anthropic",
        "claude-a",
        buddy_id=buddy.id,
        path=db_path,
    )
    db.add_message(conversation.id, "user", "hello", path=db_path)

    dry_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--database",
            str(db_path),
            "--buddy-id",
            buddy.id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dry_report = json.loads(dry_run.stdout)

    assert dry_report["mode"] == "dry-run"
    assert dry_report["targets"][0]["pending_message_count"] == 1
    assert db.get_buddy_memory(buddy.id, db_path) is None
    assert backup_path.exists() is False

    applied = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--database",
            str(db_path),
            "--buddy-id",
            buddy.id,
            "--apply",
            "--backup",
            str(backup_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    applied_report = json.loads(applied.stdout)

    assert applied_report["mode"] == "apply"
    assert applied_report["pending_message_counts"] == {buddy.id: 0}
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert len(db.messages_newer_than_watermark_for_buddy(buddy.id, db_path)) == 0
    assert len(db.list_messages(conversation.id, db_path)) == 1

    backup_memory = db.get_buddy_memory(buddy.id, backup_path)
    assert backup_memory is None
    assert len(db.list_messages(conversation.id, backup_path)) == 1


def test_recovery_script_refuses_apply_without_backup(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--database",
            str(tmp_path / "chat.db"),
            "--buddy-id",
            "buddy",
            "--apply",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--apply requires --backup" in result.stderr
