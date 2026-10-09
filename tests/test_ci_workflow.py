"""Offline guards for third-party CI action references."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_setup_uv_is_pinned_to_an_immutable_commit() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = re.search(
        r"^\s+uses: astral-sh/setup-uv@([^\s#]+)", workflow, flags=re.MULTILINE
    )
    assert match is not None, "CI must install uv through setup-uv"
    assert re.fullmatch(r"[0-9a-f]{40}", match.group(1)), (
        "Verify the upstream release, then pin its full commit SHA; "
        "a guessed major-version tag can prevent the entire job from starting"
    )
