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

def test_ensure_creates_workspace_and_is_idempotent(tw_root: Path) -> None:
    first = ensure_workspace()
    second = ensure_workspace()

    assert first.root == tw_root
    assert second.root == tw_root
    assert (tw_root / "config.toml").exists()
    assert (tw_root / "profile" / "persona.md").exists()
    assert (tw_root / "identity_styles").exists()
    assert (tw_root / "db" / "content.sqlite").exists()

    config = load_config(tw_root)
    assert config.default_language == "en"
    assert config.llm_mode == "auto"
    assert config.llm_model == "gpt-5.5"
    assert config.llm_reasoning_effort == "xhigh"
    assert config.llm_speed == "fast"
    assert config.llm_codex_timeout_seconds == 600
    assert config.x_provider == "none"
    assert config.x_readonly is True

    with sqlite3.connect(tw_root / "db" / "content.sqlite") as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type in ('table', 'view')"
            )
        }
    assert {
        "projects",
        "ideas",
        "drafts",
        "posts",
        "sources",
        "telegram_messages",
        "identity_style_profiles",
        "identity_style_examples",
        "processed_style_examples",
        "drafts_fts",
        "telegram_messages_fts",
    } <= tables

def test_legacy_auto_language_normalizes_to_english(tw_root: Path) -> None:
    ensure_workspace()
    (tw_root / "config.toml").write_text('default_language = "auto"\n', encoding="utf-8")

    config = load_config(tw_root)

    assert config.default_language == "en"

def test_project_context_is_central_and_project_directory_is_unchanged(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "sample-project"
    project.mkdir()
    (project / "README.md").write_text("# Sample\n\nPublic repo context.\n", encoding="utf-8")
    before = {p.relative_to(project) for p in project.rglob("*")}

    ensure_workspace()
    detected = detect_project(project)
    context = refresh_project_context(detected, force=True)

    after = {p.relative_to(project) for p in project.rglob("*")}
    project_dir = tw_root / "projects" / detected.id
    assert before == after
    assert detected.id.startswith("sample-project-")
    assert (project_dir / "context.md").exists()
    assert (project_dir / "recent_changes.md").exists()
    assert (project_dir / "public_angle.md").exists()
    assert "Sample" in context.summary

def test_idea_cli_search_and_fts(tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "ml-infra"
    project.mkdir()
    ensure_workspace()

    assert run_cli(["idea", "compiler errors taught me more than the tutorial"], cwd=project) == 0
    output = capsys.readouterr().out
    assert "idea_" in output

    assert run_cli(["search", "compiler"], cwd=project) == 0
    search_output = capsys.readouterr().out
    assert "compiler errors" in search_output

def test_review_redacts_secrets_and_detects_forbidden_phrases() -> None:
    text = "X_BEARER_TOKEN=abc123\nthis is important to note"
    redacted = redact_secrets(text)
    assert "abc123" not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert contains_forbidden_phrase(text)
