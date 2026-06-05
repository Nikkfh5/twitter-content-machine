from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from twitter_content_machine import mcp_server
from twitter_content_machine.cli import run_cli
from twitter_content_machine.config import load_config
from twitter_content_machine.db import connect_db
from twitter_content_machine.drafting import create_draft
from twitter_content_machine.project_context import detect_project, refresh_project_context
from twitter_content_machine.review import contains_forbidden_phrase, redact_secrets
from twitter_content_machine.workspace import ensure_workspace
from twitter_content_machine.x_read import sync_posted


@pytest.fixture()
def tw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "twitter-system"
    monkeypatch.setenv("TWITTER_SYSTEM_ROOT", str(root))
    monkeypatch.setenv("TW_TEST_FIXED_NOW", "2026-06-06T21:30:45")
    return root


def test_ensure_creates_workspace_and_is_idempotent(tw_root: Path) -> None:
    first = ensure_workspace()
    second = ensure_workspace()

    assert first.root == tw_root
    assert second.root == tw_root
    assert (tw_root / "config.toml").exists()
    assert (tw_root / "profile" / "persona.md").exists()
    assert (tw_root / "db" / "content.sqlite").exists()

    config = load_config(tw_root)
    assert config.default_language == "auto"
    assert config.x_provider == "none"
    assert config.x_readonly is True

    with sqlite3.connect(tw_root / "db" / "content.sqlite") as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type in ('table', 'view')"
            )
        }
    assert {"projects", "ideas", "drafts", "posts", "sources", "drafts_fts"} <= tables


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


def test_draft_creates_expected_files_without_llm(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "quant-notes"
    project.mkdir()
    (project / "README.md").write_text("# Quant Notes\n", encoding="utf-8")
    ensure_workspace()

    draft = create_draft(
        text="I realized my backtest execution assumptions are fake",
        draft_type="short",
        cwd=project,
    )

    expected = {
        "00_raw_input.md",
        "01_context_used.md",
        "02_brief.md",
        "03_variants.md",
        "04_critique.md",
        "05_selected.md",
        "06_final_candidate.md",
        "prompt_to_codex.md",
        "meta.yaml",
    }
    assert draft.folder.name.startswith("20260606-213045-backtest-execution-assumptions-")
    assert expected == {p.name for p in draft.folder.iterdir() if p.is_file()}
    assert "Variant A" in (draft.folder / "03_variants.md").read_text(encoding="utf-8")
    assert "important to note" not in (
        draft.folder / "06_final_candidate.md"
    ).read_text(encoding="utf-8").lower()

    with connect_db() as conn:
        row = conn.execute("select id, status, folder_path from drafts").fetchone()
    assert row["id"] == draft.id
    assert row["status"] == "draft"
    assert Path(row["folder_path"]) == draft.folder


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


def test_sync_posted_disabled_exits_cleanly(tw_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_workspace()
    result = sync_posted()
    assert result.imported == 0
    assert "disabled" in result.message.lower()

    assert run_cli(["sync-posted"]) == 0
    assert "read-only X sync is disabled" in capsys.readouterr().out


def test_review_redacts_secrets_and_detects_forbidden_phrases() -> None:
    text = "X_BEARER_TOKEN=abc123\nthis is important to note"
    redacted = redact_secrets(text)
    assert "abc123" not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert contains_forbidden_phrase(text)


def test_mcp_tool_registry_has_no_publish_tool() -> None:
    tool_names = mcp_server.tool_names()
    assert "tw_create_draft" in tool_names
    assert "tw_sync_posted_readonly" in tool_names
    assert all("publish" not in name and "post_to_x" not in name for name in tool_names)


def test_open_latest_resolves_existing_draft_without_gui(tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "systems"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("this broke because the cache key ignored branch", "build-log", project)

    assert run_cli(["open", "latest", "--print-path"], cwd=project) == 0
    output = capsys.readouterr().out
    assert str(draft.folder) in output
