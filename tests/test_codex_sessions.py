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

def test_codex_prepare_from_active_draft_creates_content_session(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "codex-session-project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Coding Agent\n\nRun tests.\n", encoding="utf-8")
    before = {p.relative_to(project) for p in project.rglob("*")}
    ensure_workspace()
    (tw_root / "profile" / "style_gold.md").write_text("# Style Gold\n\nstyle examples", encoding="utf-8")
    (tw_root / "profile" / "content_gold.md").write_text("# Content Gold\n\ncontent examples", encoding="utf-8")
    draft = create_draft("article note about validation leaks", "article-note", project, no_llm=True)

    assert run_cli(["codex", "--prepare", "--thread"], cwd=project) == 0
    output = capsys.readouterr().out

    after = {p.relative_to(project) for p in project.rglob("*")}
    assert before == after
    session_dirs = list((tw_root / "codex_sessions").glob("*"))
    assert session_dirs
    session = sorted(session_dirs)[-1]
    assert str(session) in output
    assert (session / "AGENTS.md").exists()
    assert (session / ".codex_home" / "AGENTS.md").exists()
    assert (session / ".codex_home" / "config.toml").exists()
    assert (session / "TASK.md").exists()
    assert (session / "CONTEXT_BUNDLE.md").exists()
    assert (session / "INPUT.md").exists()
    assert (session / "OUTPUT_SCHEMA.md").exists()
    assert (session / "output").is_dir()
    assert (tw_root / "state" / "current_codex_session.txt").read_text(encoding="utf-8").strip() == str(session)
    assert "article note about validation leaks" in (session / "INPUT.md").read_text(encoding="utf-8")
    assert "Style Gold" in (session / "CONTEXT_BUNDLE.md").read_text(encoding="utf-8")
    assert "Content Gold" in (session / "CONTEXT_BUNDLE.md").read_text(encoding="utf-8")
    assert "Run tests" not in (session / "AGENTS.md").read_text(encoding="utf-8")
    assert "Default output language is English" in (session / "AGENTS.md").read_text(encoding="utf-8")
    assert "write final candidates in English" in (session / "TASK.md").read_text(encoding="utf-8")
    assert "Write the thread in English by default" in (session / "OUTPUT_SCHEMA.md").read_text(encoding="utf-8")
    assert draft.id in (session / "TASK.md").read_text(encoding="utf-8")

def test_codex_prepare_from_file_uses_file_as_input(
    tw_root: Path, tmp_path: Path
) -> None:
    source = tmp_path / "article_notes.md"
    source.write_text("# Notes\n\nThis article is about execution realism.", encoding="utf-8")
    ensure_workspace()

    assert run_cli(["codex", "--prepare", "--file", str(source), "--final-post"]) == 0

    session = sorted((tw_root / "codex_sessions").glob("*"))[-1]
    assert "execution realism" in (session / "INPUT.md").read_text(encoding="utf-8")
    assert "final-post" in (session / "TASK.md").read_text(encoding="utf-8")

def test_codex_run_invokes_codex_from_session_folder(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "run-codex-session"
    project.mkdir()
    ensure_workspace()
    create_draft("small note about fills", "short", project, no_llm=True)
    calls = []

    class Completed:
        returncode = 0

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.exe")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("twitter_content_machine.codex_session.subprocess.run", fake_run)

    assert run_cli(["codex", "--run"], cwd=project) == 0

    assert calls
    command, kwargs = calls[0]
    session = Path(kwargs["cwd"])
    assert command == ["C:/bin/codex.exe"]
    assert session.parent == tw_root / "codex_sessions"
    assert "CODEX_HOME" not in kwargs["env"]

    (session / ".codex_home" / "auth.json").write_text("{}", encoding="utf-8")
    run_codex_session(CodexSessionResult(session, ["C:/bin/codex.exe"], False, None))
    _, isolated_kwargs = calls[-1]
    assert isolated_kwargs["env"]["CODEX_HOME"] == str(session / ".codex_home")
