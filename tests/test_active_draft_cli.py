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

def test_open_latest_resolves_existing_draft_without_gui(tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "systems"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("this broke because the cache key ignored branch", "build-log", project, no_llm=True)

    assert run_cli(["open", "latest", "--print-path"], cwd=project) == 0
    output = capsys.readouterr().out
    assert str(draft.folder) in output

def test_current_draft_commands_default_to_active_draft(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "active-draft"
    project.mkdir()
    ensure_workspace()

    assert run_cli(["draft", "--no-llm", "execution assumptions broke the backtest"], cwd=project) == 0
    capsys.readouterr()

    assert run_cli(["path"], cwd=project) == 0
    path_output = capsys.readouterr().out
    assert "draft_" in path_output
    assert "06_final_candidate.md" not in path_output

    assert run_cli(["show"], cwd=project) == 0
    show_output = capsys.readouterr().out
    assert "execution assumptions" in show_output

    assert run_cli(["ready"], cwd=project) == 0
    ready_output = capsys.readouterr().out
    assert "ready" in ready_output
    with connect_db() as conn:
        row = conn.execute("select status from drafts where id = ?", (resolve_draft_id("latest"),)).fetchone()
    assert row["status"] == "ready"

def test_use_switches_current_draft_by_list_number(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "switch-draft"
    project.mkdir()
    ensure_workspace()

    older = create_draft("older thought about fills", "short", project, no_llm=True)
    newer = create_draft("newer thought about validation", "short", project, no_llm=True)

    assert run_cli(["drafts", "--limit", "2"], cwd=project) == 0
    listing = capsys.readouterr().out
    assert "* 1" in listing
    assert newer.id in listing
    assert older.id in listing

    assert run_cli(["use", "2"], cwd=project) == 0
    use_output = capsys.readouterr().out
    assert older.id in use_output

    assert run_cli(["show"], cwd=project) == 0
    show_output = capsys.readouterr().out
    assert "older thought" in show_output

def test_review_layers_default_to_current_draft(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "current-review"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("I stopped trusting fake fills", "short", project, no_llm=True)

    assert run_cli(["algo"], cwd=project) == 0
    assert run_cli(["review"], cwd=project) == 0
    assert run_cli(["algo-review"], cwd=project) == 0
    assert run_cli(["media-plan"], cwd=project) == 0
    assert run_cli(["distribution-plan"], cwd=project) == 0

    assert (draft.folder / "07_algorithm_review.md").exists()
    assert (draft.folder / "08_media_plan.md").exists()
    assert (draft.folder / "09_distribution_plan.md").exists()

def test_bare_tw_text_creates_adaptive_draft(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "bare-scribe"
    project.mkdir()
    ensure_workspace()
    payload = {
        "variants": [
            {
                "id": "A",
                "name": "direct_raw",
                "text": "Validation failure note.",
                "intent": "dwell",
                "why_it_might_work": "specific",
                "risks": [],
            }
        ],
        "critique": {
            "real_point": "ok",
            "too_generic": False,
            "overclaim_risk": "low",
            "financial_advice_risk": "low",
            "confidentiality_risk": "low",
            "repetition_risk": "low",
            "identity_style_risk": "low",
            "algorithm_fit": "ok",
        },
        "selected_variant_id": "A",
        "final_candidate": "Validation failure note.",
        "media_suggestion": {"use_media": False, "type": "none", "reason": "none"},
        "manual_notes": [],
    }

    class Completed:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.exe")
    monkeypatch.setattr(
        "twitter_content_machine.llm.detect_codex_capabilities",
        lambda command="codex": {"exec": True, "cd": True, "model": True, "config": True},
    )
    monkeypatch.setattr("twitter_content_machine.llm.subprocess.run", lambda command, **kwargs: Completed())

    assert run_cli(["I want to write about a validation failure in this project"], cwd=project) == 0
    output = capsys.readouterr().out

    assert "Validation failure note." in output
    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select type, final_text from drafts where id = ?", (draft_id,)).fetchone()
    assert row["type"] == "adaptive"
    assert row["final_text"] == "Validation failure note."

def test_edit_current_draft_uses_codex_and_updates_final_candidate(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "edit-current"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("Long draft about execution assumptions.", "short", project, no_llm=True)

    class Completed:
        returncode = 0
        stdout = '{"final_candidate": "Shorter execution note."}'
        stderr = 'debug echoed schema: {"final_candidate": "..."}'

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.exe")
    monkeypatch.setattr("twitter_content_machine.llm.detect_codex_capabilities", lambda command="codex": {"exec": True, "cd": True, "model": True, "config": False})
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("twitter_content_machine.editing.subprocess.run", fake_run)

    assert run_cli(["edit", "make it shorter"], cwd=project) == 0
    output = capsys.readouterr().out

    assert "Shorter execution note." in output
    assert calls
    assert calls[0][0][-1] == "-"
    assert calls[0][1]["input"]
    assert "Default output language is English" in calls[0][1]["input"]
    assert (draft.folder / "06_final_candidate.md").read_text(encoding="utf-8") == "Shorter execution note.\n"
    assert (draft.folder / "17_edit_request.md").exists()
    assert (draft.folder / "18_edit_raw_output.md").exists()
    assert (draft.folder / "19_edit_parse_report.md").exists()
    assert list((draft.folder / "revisions").glob("*.md"))
    with connect_db() as conn:
        row = conn.execute("select final_text from drafts where id = ?", (draft.id,)).fetchone()
    assert row["final_text"] == "Shorter execution note."

def test_smart_search_uses_codex_over_memory_candidates(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "smart-search"
    project.mkdir()
    ensure_workspace()
    assert run_cli(["idea", "execution assumptions erased the fake edge"], cwd=project) == 0
    capsys.readouterr()

    class Completed:
        returncode = 0
        stdout = "Best match: idea about execution assumptions."
        stderr = ""

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.exe")
    monkeypatch.setattr("twitter_content_machine.llm.detect_codex_capabilities", lambda command="codex": {"exec": True, "cd": True, "model": True, "config": False})
    monkeypatch.setattr("twitter_content_machine.smart_search.subprocess.run", lambda command, **kwargs: Completed())

    assert run_cli(["search", "--smart", "execution assumptions"], cwd=project) == 0
    output = capsys.readouterr().out

    assert "Best match" in output
    search_dirs = list((tw_root / "searches").glob("*"))
    assert search_dirs
    latest = sorted(search_dirs)[-1]
    assert (latest / "01_candidates.md").exists()
    assert (latest / "02_codex_request.md").exists()
    assert (latest / "03_codex_raw_output.md").exists()

def test_style_gold_import_copies_style_and_content_gold(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack = tmp_path / "style_content_gold.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("style_gold.md", "# Style Gold\n\nstyle examples")
        zf.writestr("content_gold.md", "# Content Gold\n\ncontent examples")
    ensure_workspace()

    assert run_cli(["style-gold-import", str(pack)]) == 0
    output = capsys.readouterr().out

    assert "style_gold.md" in output
    assert (tw_root / "profile" / "style_gold.md").read_text(encoding="utf-8").startswith("# Style Gold")
    assert (tw_root / "profile" / "content_gold.md").read_text(encoding="utf-8").startswith("# Content Gold")
    assert (tw_root / "profile" / "style_content_gold_report.md").exists()
