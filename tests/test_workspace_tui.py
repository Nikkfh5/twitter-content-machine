from __future__ import annotations

from twitter_content_machine.workspace_tui import _split_screen


def test_split_screen_returns_keys_used_by_tui_refresh() -> None:
    sections = _split_screen(
        """Content Workspace

Status: active/needs_user
Next action: /continue --run - run Codex

Draft preview
draft text

Summary
summary text

Problems
- problem

Decisions
- decision

Progress
[x] create draft files

Files
- draft: C:/draft

Recent activity
- Waiting for your next command
"""
    )

    for key in [
        "state",
        "progress",
        "Draft preview",
        "Summary",
        "Problems",
        "Decisions",
        "Files",
        "Recent activity",
        "next",
    ]:
        assert key in sections
    assert sections["progress"] == "[x] create draft files"
    assert sections["next"] == "/continue --run - run Codex"
