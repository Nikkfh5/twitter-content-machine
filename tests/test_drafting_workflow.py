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

def test_draft_creates_expected_files_without_llm(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "quant-notes"
    project.mkdir()
    (project / "README.md").write_text("# Quant Notes\n", encoding="utf-8")
    ensure_workspace()

    draft = create_draft(
        text="I realized my backtest execution assumptions are fake",
        draft_type="short",
        cwd=project,
        no_llm=True,
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
    assert expected <= {p.name for p in draft.folder.iterdir() if p.is_file()}
    assert "Variant A" in (draft.folder / "03_variants.md").read_text(encoding="utf-8")
    assert "important to note" not in (
        draft.folder / "06_final_candidate.md"
    ).read_text(encoding="utf-8").lower()

    with connect_db() as conn:
        row = conn.execute("select id, status, folder_path from drafts").fetchone()
    assert row["id"] == draft.id
    assert row["status"] == "draft"
    assert Path(row["folder_path"]) == draft.folder

def test_plain_draft_defaults_to_adaptive_format(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "adaptive-default"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "--no-llm", "raw project thought with enough context"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select type, folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    request = (folder / "14_llm_request.md").read_text(encoding="utf-8")
    meta = (folder / "meta.yaml").read_text(encoding="utf-8")

    assert row["type"] == "adaptive"
    assert "type: adaptive" in meta
    assert "Do not make the post artificially short" in request
    assert "2-5 short paragraphs" in request

def test_adaptive_draft_writes_format_decision_artifact(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "format-decision"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "--no-llm", "I fixed a validation bug and need a build log about what broke"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    decision = (folder / "FORMAT_DECISION.md").read_text(encoding="utf-8")
    request = (folder / "14_llm_request.md").read_text(encoding="utf-8")
    bundle = json.loads((folder / "13_context_bundle.json").read_text(encoding="utf-8"))

    assert "best_format: build-log" in decision
    assert "decision_source: adaptive-heuristic" in decision
    assert "FORMAT_DECISION.md" in request
    assert "best_format: build-log" in request
    assert bundle["format_decision"]["best_format"] == "build-log"

def test_explicit_short_format_records_user_override(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "format-override"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "--no-llm", "--short", "small note"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    decision = (folder / "FORMAT_DECISION.md").read_text(encoding="utf-8")

    assert "requested_format: short" in decision
    assert "best_format: short" in decision
    assert "decision_source: explicit-user-format" in decision

def test_short_flag_keeps_explicit_short_format(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "explicit-short"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "--no-llm", "--short", "small note"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select type from drafts where id = ?", (draft_id,)).fetchone()

    assert row["type"] == "short"

def test_context_only_draft_creates_bundle_and_isolated_generation_workspace(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "source-project"
    project.mkdir()
    (project / "README.md").write_text("# Source Project\n\nPublic context.\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# Coding Instructions\n\nDo code things.\n", encoding="utf-8")
    (project / ".env").write_text("SECRET_TOKEN=abc123\n", encoding="utf-8")
    before = {p.relative_to(project) for p in project.rglob("*")}
    ensure_workspace()

    assert (
        run_cli(
            [
                "draft",
                "--context-only",
                "--short",
                "--identity-strength",
                "0.35",
                "I realized execution assumptions matter",
            ],
            cwd=project,
        )
        == 0
    )

    after = {p.relative_to(project) for p in project.rglob("*")}
    assert before == after
    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    bundle_md = (folder / "13_context_bundle.md").read_text(encoding="utf-8")
    bundle_json = json.loads((folder / "13_context_bundle.json").read_text(encoding="utf-8"))

    assert (folder / "14_llm_request.md").exists()
    assert (folder / "16_llm_parse_report.md").exists()
    assert (folder / "AGENTS.md").exists()
    assert (folder / "AGENTS.override.md").exists()
    assert (folder / ".codex_home" / "AGENTS.md").exists()
    assert (folder / ".codex_home" / "config.toml").exists()
    assert "Source Project" in bundle_md
    assert "SECRET_TOKEN" not in bundle_md
    request_text = (folder / "14_llm_request.md").read_text(encoding="utf-8")
    assert len(request_text) < len(bundle_md)
    assert "13_context_bundle.md" in request_text
    assert "Return strict JSON only" in request_text
    assert "Output language: English" in request_text
    assert "translate/adapt the meaning into English" in request_text
    assert bundle_json["task"]["cwd"] == str(project.resolve())
    assert bundle_json["source_manifest"]
    override = (folder / "AGENTS.override.md").read_text(encoding="utf-8")
    assert "Do not inspect parent source repositories" in override
    assert "Do code things" not in override

def test_default_draft_requires_codex_when_no_llm_flag_is_absent(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "strict-codex"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "raw thought"], cwd=project) == 1
    output = capsys.readouterr()

    assert "not found" in output.err.lower()
    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    report = (folder / "16_llm_parse_report.md").read_text(encoding="utf-8")
    assert "ok: false" in report
    assert "not found" in report.lower()

def test_draft_cli_prints_codex_progress_to_stderr(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "progress-project"
    project.mkdir()
    ensure_workspace()
    (tw_root / "config.toml").write_text(
        """
[llm]
codex_timeout_seconds = 5
codex_progress_interval_seconds = 0.01
""",
        encoding="utf-8",
    )
    payload = {
        "variants": [
            {
                "id": "A",
                "name": "direct_raw",
                "text": "English draft.",
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
        "final_candidate": "English draft.",
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

    def fake_run(command, **kwargs):
        time.sleep(0.05)
        return Completed()

    monkeypatch.setattr("twitter_content_machine.llm.subprocess.run", fake_run)

    assert run_cli(["draft", "русская мысль"], cwd=project) == 0
    captured = capsys.readouterr()

    assert "English draft." in captured.out
    assert "tw: codex started" in captured.err
    assert "tw: codex still working" in captured.err
    assert "tw: codex finished" in captured.err

def test_no_llm_keeps_manual_fallback_and_runs_algorithm_review_by_default(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "no-llm"
    project.mkdir()
    ensure_workspace()
    monkeypatch.setattr("twitter_content_machine.llm.resolve_codex_command", lambda command: None)

    assert run_cli(["draft", "--no-llm", "raw thought"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    assert (folder / "07_algorithm_review.md").exists()
    assert (folder / "08_media_plan.md").exists()
    assert (folder / "09_distribution_plan.md").exists()

def test_default_draft_uses_tg_crypto_clean_identity_when_profile_exists(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "default-identity"
    project.mkdir()
    ensure_workspace()
    now = "2026-06-07T00:00:00"
    with connect_db() as conn:
        conn.execute(
            "insert into identity_style_profiles(profile_name, created_at, updated_at, summary, default_strength, status) values(?, ?, ?, ?, ?, ?)",
            ("tg_crypto_clean", now, now, "ready", 0.35, "built"),
        )
        conn.execute(
            """
            insert into telegram_messages(id, profile_name, telegram_message_id, date, source_role, forwarded_from,
              author, text_clean, text_raw_hash, length, reactions, has_photo, media_type, risk_flags, labels, imported_at)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tg_crypto_clean:1",
                "tg_crypto_clean",
                "1",
                now,
                "own_original",
                "",
                "",
                "кажется, я понял где ломается проверка: не в модели, а в протоколе",
                "hash",
                72,
                0,
                0,
                "",
                "[]",
                "",
                now,
            ),
        )
        conn.execute(
            "insert into identity_style_examples(id, profile_name, telegram_message_id, label, note, created_at) values(?, ?, ?, ?, ?, ?)",
            ("tg_crypto_clean:1:auto_gold", "tg_crypto_clean", "1", "auto_gold", "test", now),
        )

    assert run_cli(["draft", "--no-llm", "raw thought"], cwd=project) == 0

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])
    assert (folder / "10_identity_style_review.md").exists()
    assert (folder / "11_examples_used.md").exists()
    assert (folder / "12_risk_flags.md").exists()
    assert "tg_crypto_clean" in (folder / "meta.yaml").read_text(encoding="utf-8")

def test_print_prompt_path_outputs_llm_request_path(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "prompt-path"
    project.mkdir()
    ensure_workspace()

    assert run_cli(["draft", "--context-only", "--print-prompt-path", "--short", "raw idea"], cwd=project) == 0
    output = capsys.readouterr().out

    assert "14_llm_request.md" in output
