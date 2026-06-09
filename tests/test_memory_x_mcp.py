from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
import shutil
import json
import zipfile

import pytest

from twitter_content_machine import mcp_server
from twitter_content_machine.cli import run_cli
from twitter_content_machine.config import load_config
from twitter_content_machine.codex_session import CodexSessionResult, run_codex_session
from twitter_content_machine.db import connect_db, resolve_draft_id
from twitter_content_machine.drafting import create_draft, set_draft_status
from twitter_content_machine.llm import build_codex_invocation_plan, resolve_codex_command
from twitter_content_machine.llm_parsing import parse_llm_output
from twitter_content_machine.project_context import detect_project, refresh_project_context
from twitter_content_machine.review import contains_forbidden_phrase, redact_secrets
from twitter_content_machine.workspace import ensure_workspace
from twitter_content_machine.x_read import sync_posted

def test_sync_posted_disabled_exits_cleanly(tw_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_workspace()
    result = sync_posted()
    assert result.imported == 0
    assert "disabled" in result.message.lower()

    assert run_cli(["sync-posted"]) == 0
    assert "read-only X sync is disabled" in capsys.readouterr().out

def test_mcp_tool_registry_has_no_publish_tool() -> None:
    tool_names = mcp_server.tool_names()
    assert "tw_create_draft" in tool_names
    assert "tw_sync_posted_readonly" in tool_names
    assert all("publish" not in name and "post_to_x" not in name for name in tool_names)

def test_mcp_registry_exposes_identity_tools_without_publish() -> None:
    tool_names = mcp_server.tool_names()
    for name in [
        "tw_algo_review",
        "tw_style_review",
        "tw_import_telegram",
        "tw_style_build",
        "tw_style_learn",
        "tw_style_curate",
    ]:
        assert name in tool_names
    assert all("publish" not in name and "post_to_x" not in name for name in tool_names)

def test_project_aware_memory_search_prioritizes_same_project(tw_root: Path, tmp_path: Path) -> None:
    project_a = tmp_path / "alpha"
    project_b = tmp_path / "beta"
    project_a.mkdir()
    project_b.mkdir()
    ensure_workspace()
    assert run_cli(["idea", "same keyword from alpha project"], cwd=project_a) == 0
    assert run_cli(["idea", "same keyword from beta project"], cwd=project_b) == 0
    project = detect_project(project_b)

    rows = mcp_server.tw_search_memory("same keyword", project_id=project.id, limit=5)

    assert rows[0]["project_id"] == project.id
    assert "beta project" in rows[0]["text"]

def test_x_sync_imports_mocked_readonly_posts(tw_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_workspace()
    config_path = tw_root / "config.toml"
    config_path.write_text(
        """
default_language = "auto"

[x]
provider = "x_api"
user_id = "42"
readonly = true
max_import = 10
exclude_retweets = true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")

    class FakeResponse:
        status = 200

        def read(self) -> bytes:
            return json.dumps(
                {
                    "data": [
                        {
                            "id": "post1",
                            "text": "execution assumptions matter",
                            "created_at": "2026-06-07T00:00:00Z",
                            "conversation_id": "post1",
                            "public_metrics": {"like_count": 3},
                        }
                    ]
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=0):
        assert request.full_url.startswith("https://api.x.com/2/users/42/tweets")
        assert request.get_header("Authorization") == "Bearer test-token"
        return FakeResponse()

    monkeypatch.setattr("twitter_content_machine.x_read.request.urlopen", fake_urlopen)

    result = sync_posted()

    assert result.imported == 1
    with connect_db() as conn:
        row = conn.execute("select platform_post_id, text from posts where platform_post_id = 'post1'").fetchone()
    assert row["text"] == "execution assumptions matter"

def test_x_read_disabled_and_readonly_false_behaviors(tw_root: Path) -> None:
    ensure_workspace()
    assert sync_posted().imported == 0
    config_path = tw_root / "config.toml"
    config_path.write_text(
        """
[x]
provider = "x_api"
readonly = false
""",
        encoding="utf-8",
    )

    result = sync_posted()

    assert "Refusing" in result.message
