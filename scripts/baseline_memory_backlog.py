"""Baseline abandoned buddy-memory backlogs without deleting transcripts."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import sys

from aol_llm.config import database_path
from aol_llm.storage import db


def main() -> int:
    args = _parse_args()
    try:
        candidates = db.preview_buddy_memory_baselines(args.buddy_id, args.database)
        before_counts = _transcript_counts(candidates)
        report: dict[str, object] = {
            "mode": "apply" if args.apply else "dry-run",
            "database": str(args.database),
            "targets": [_candidate_report(item, args.database) for item in candidates],
            "transcript_counts": before_counts,
        }
        if not args.apply:
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        assert args.backup is not None
        _backup_database(args.database, args.backup)
        db.baseline_empty_buddy_memories(args.buddy_id, args.database)
        after = db.preview_buddy_memory_baselines(args.buddy_id, args.database)
        after_counts = _transcript_counts(after)
        pending_counts = {
            item.buddy_id: len(
                db.messages_newer_than_watermark_for_buddy(
                    item.buddy_id,
                    args.database,
                )
            )
            for item in after
        }
        if after_counts != before_counts or any(pending_counts.values()):
            raise RuntimeError("post-apply transcript or watermark verification failed")
        report["backup"] = str(args.backup)
        report["pending_message_counts"] = pending_counts
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (KeyError, OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Baseline selected empty buddy memories at their newest stored messages. "
            "The default is a read-only dry run."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=database_path(),
        help="SQLite database path (default: the configured AOL-LLM data path)",
    )
    parser.add_argument(
        "--buddy-id",
        action="append",
        required=True,
        help="Buddy id to baseline; repeat for each selected buddy",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the required backup and apply the baseline transaction",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        help="New private SQLite backup path; required with --apply",
    )
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply requires --backup")
    if not args.apply and args.backup is not None:
        parser.error("--backup is valid only with --apply")
    return args


def _candidate_report(
    candidate: db.BuddyMemoryBaseline,
    path: Path,
) -> dict[str, object]:
    report = asdict(candidate)
    report["pending_message_count"] = len(
        db.messages_newer_than_watermark_for_buddy(candidate.buddy_id, path)
    )
    return report


def _transcript_counts(
    candidates: list[db.BuddyMemoryBaseline],
) -> dict[str, int]:
    return {
        "conversations": sum(item.conversation_count for item in candidates),
        "messages": sum(item.message_count for item in candidates),
    }


def _backup_database(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        raise ValueError("backup path must differ from database path")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(target) as target_connection:
                source_connection.backup(target_connection)
        os.chmod(target, 0o600)
        with sqlite3.connect(target) as backup_connection:
            result = backup_connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError("backup integrity check failed")
    except (OSError, RuntimeError, sqlite3.Error):
        target.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
