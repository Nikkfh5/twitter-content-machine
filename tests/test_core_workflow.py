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
from twitter_content_machine.drafting import create_draft
from twitter_content_machine.llm import build_codex_invocation_plan, resolve_codex_command
from twitter_content_machine.llm_parsing import parse_llm_output
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


def test_llm_parser_handles_plain_and_fenced_json() -> None:
    payload = {
        "variants": [
            {
                "id": "A",
                "name": "direct_raw",
                "text": "Small note.",
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
        "final_candidate": "Small note.",
        "media_suggestion": {"use_media": False, "type": "none", "reason": "none"},
        "manual_notes": [],
    }

    parsed = parse_llm_output("```json\n" + json.dumps(payload) + "\n```")

    assert parsed.ok is True
    assert parsed.data["final_candidate"] == "Small note."


def test_llm_parser_prefers_leading_json_over_schema_echo_in_stderr() -> None:
    good = {
        "variants": [
            {
                "id": "A",
                "name": "direct_raw",
                "text": "Real draft.",
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
        "final_candidate": "Real draft.",
        "media_suggestion": {"use_media": False, "type": "none", "reason": "none"},
        "manual_notes": [],
    }
    schema_echo = '```json\n{"final_candidate": "..."}\n```'

    parsed = parse_llm_output(json.dumps(good) + "\n\nSTDERR:\n" + schema_echo)

    assert parsed.ok is True
    assert parsed.data["final_candidate"] == "Real draft."


def test_llm_parser_reports_invalid_output() -> None:
    parsed = parse_llm_output("not json")

    assert parsed.ok is False
    assert "No JSON object found" in parsed.error


def test_codex_invocation_plan_uses_draft_folder_and_isolated_home(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ensure_workspace()

    class Completed:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(command, **kwargs):
        if command == ["C:/bin/codex.exe", "--help"]:
            return Completed("Usage\nCommands:\n  exec\n")
        if command == ["C:/bin/codex.exe", "exec", "--help"]:
            return Completed("Usage\n  --cd <DIR>\n  --model <MODEL>\n  --config <KEY=VALUE>\n")
        return Completed("")

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.exe")
    monkeypatch.setattr("twitter_content_machine.llm.subprocess.run", fake_run)

    draft_folder = tmp_path / "draft"
    draft_folder.mkdir()
    raw_request = '{"final_candidate": "x"} & echo should-not-run'
    plan = build_codex_invocation_plan(raw_request, draft_folder, load_config(tw_root))

    assert plan.cwd == draft_folder
    assert "CODEX_HOME" not in plan.env
    assert "--cd" in plan.command
    assert str(draft_folder) in plan.command
    assert "--model" in plan.command
    assert "gpt-5.5" in plan.command
    assert "--config" in plan.command
    assert 'model_reasoning_effort="xhigh"' in plan.command
    assert 'service_tier="fast"' in plan.command
    assert plan.command[-1] == "-"
    assert raw_request not in plan.command

    (draft_folder / ".codex_home").mkdir()
    (draft_folder / ".codex_home" / "auth.json").write_text("{}", encoding="utf-8")
    isolated_plan = build_codex_invocation_plan(raw_request, draft_folder, load_config(tw_root))
    assert isolated_plan.env["CODEX_HOME"] == str(draft_folder / ".codex_home")


def test_codex_runner_sends_prompt_via_stdin_and_reports_nonzero_stderr(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ensure_workspace()
    request = tmp_path / "14_llm_request.md"
    request.write_text('{"prompt": "contains & shell chars"}', encoding="utf-8")
    draft_folder = tmp_path / "draft"
    draft_folder.mkdir()
    calls = []

    class Completed:
        returncode = 2
        stdout = ""
        stderr = "codex failed before model output"

    monkeypatch.setattr("twitter_content_machine.llm.shutil.which", lambda command: "C:/bin/codex.cmd")
    monkeypatch.setattr(
        "twitter_content_machine.llm.detect_codex_capabilities",
        lambda command="codex": {"exec": True, "cd": True, "model": True, "config": True},
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("twitter_content_machine.llm.subprocess.run", fake_run)

    from twitter_content_machine.llm import run_llm

    result = run_llm("codex", request, draft_folder, load_config(tw_root))

    assert calls
    command, kwargs = calls[0]
    assert command[-1] == "-"
    assert kwargs["input"] == '{"prompt": "contains & shell chars"}'
    assert result.ok is False
    assert "codex failed before model output" in result.message
    assert result.parsed.error == "Codex exited with code 2"


def test_codex_runner_reports_progress_while_waiting(
    tw_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ensure_workspace()
    config_path = tw_root / "config.toml"
    config_path.write_text(
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
    request = tmp_path / "14_llm_request.md"
    request.write_text('{"prompt": "slow enough for progress"}', encoding="utf-8")
    draft_folder = tmp_path / "draft"
    draft_folder.mkdir()
    progress: list[str] = []

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

    from twitter_content_machine.llm import run_llm

    result = run_llm("codex", request, draft_folder, load_config(tw_root), progress_callback=progress.append)

    assert result.ok is True
    assert any("codex started" in item for item in progress)
    assert any("codex still working" in item for item in progress)
    assert any("codex finished" in item for item in progress)


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


def test_algo_review_media_and_distribution_commands_create_review_files(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "market-systems"
    project.mkdir()
    ensure_workspace()
    draft = create_draft(
        "I misunderstood backtest fills until fees and worse execution erased the edge",
        "short",
        project,
        no_llm=True,
    )

    assert run_cli(["algo-review", "latest"], cwd=project) == 0
    assert run_cli(["media-plan", "latest"], cwd=project) == 0
    assert run_cli(["distribution-plan", "latest"], cwd=project) == 0

    algorithm_review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8")
    media_plan = (draft.folder / "08_media_plan.md").read_text(encoding="utf-8")
    distribution_plan = (draft.folder / "09_distribution_plan.md").read_text(encoding="utf-8")

    assert "Candidate retrieval fit" in algorithm_review
    assert "Machine-readable scores" in algorithm_review
    assert "Use media?" in media_plan
    assert "Post type:" in distribution_plan


def test_algo_aware_draft_runs_all_review_layers(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "cpp-infra"
    project.mkdir()
    ensure_workspace()

    assert (
        run_cli(
                [
                    "draft",
                    "--no-llm",
                    "--algo-aware",
                    "--short",
                    "Small build note: the model was less broken than the validation protocol",
            ],
            cwd=project,
        )
        == 0
    )

    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])

    assert (folder / "07_algorithm_review.md").exists()
    assert (folder / "08_media_plan.md").exists()
    assert (folder / "09_distribution_plan.md").exists()


def test_algo_review_flags_repeated_ideas(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "repeat-check"
    project.mkdir()
    ensure_workspace()
    text = "Backtesting realism improved only after I stopped trusting fake fills"
    assert run_cli(["idea", text], cwd=project) == 0
    draft = create_draft(text, "short", project, no_llm=True)

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "repeated idea risk" in review
    assert "similar memory exists" in review


def test_algo_review_rejects_crypto_financial_advice_language(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "risk"
    project.mkdir()
    ensure_workspace()
    draft = create_draft(
        "This alpha is easy money: buy now for 100x, not financial advice",
        "short",
        project,
        no_llm=True,
    )

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "financial-advice risk" in review
    assert "crypto-shill risk" in review
    assert "decision: reject" in review


def test_algo_review_does_not_match_crypto_terms_inside_normal_words(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "false-crypto-risk"
    project.mkdir()
    ensure_workspace()
    draft = create_draft(
        "The process forced the project into a more serious shape with reproducible comparisons and repeated benchmark checks.",
        "adaptive",
        project,
        no_llm=True,
    )

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "crypto-shill risk: low" in review


def test_media_plan_rejects_decorative_media(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "media"
    project.mkdir()
    ensure_workspace()
    draft = create_draft(
        "Small note: the useful lesson was that validation leaked through the feature protocol",
        "short",
        project,
        no_llm=True,
    )

    assert run_cli(["media-plan", draft.id], cwd=project) == 0
    plan = (draft.folder / "08_media_plan.md").read_text(encoding="utf-8").lower()

    assert "use media?\n- no" in plan
    assert "decorative media rejected" in plan


def test_algo_review_revises_thread_when_one_idea_is_stretched(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "thread"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("backtesting assumptions matter", "thread", project, no_llm=True)
    (draft.folder / "06_final_candidate.md").write_text(
        "\n\n".join(
            [
                "1/ Backtesting assumptions matter.",
                "2/ Backtesting assumptions matter.",
                "3/ Backtesting assumptions matter.",
                "4/ Backtesting assumptions matter.",
                "5/ Backtesting assumptions matter.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with connect_db() as conn:
        conn.execute(
            "update drafts set final_text = ? where id = ?",
            ((draft.folder / "06_final_candidate.md").read_text(encoding="utf-8"), draft.id),
        )

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "thread stretch risk" in review
    assert "decision: revise" in review


def test_tg_import_accepts_prepared_identity_pack_zip(tw_root: Path) -> None:
    pack = Path(r"C:\Users\v-353\Downloads\tg_identity_pack.zip")
    if not pack.exists():
        pytest.skip("identity pack zip not available")
    ensure_workspace()

    assert run_cli(["tg-import", str(pack), "--profile", "tg_crypto_clean"]) == 0

    profile_dir = tw_root / "identity_styles" / "tg_crypto_clean"
    assert (profile_dir / "parsed" / "telegram_messages_cleaned.jsonl").exists()
    assert (profile_dir / "identity_style_card.md").exists()
    assert (profile_dir / "anti_patterns.md").exists()
    assert (profile_dir / "import_report.md").exists()
    with connect_db() as conn:
        count = conn.execute("select count(*) from telegram_messages").fetchone()[0]
        forwarded = conn.execute(
            "select count(*) from telegram_messages where source_role = 'forwarded_other'"
        ).fetchone()[0]
    assert count > 100
    assert forwarded > 0


def test_tg_import_parses_raw_result_json_sample(tw_root: Path, tmp_path: Path) -> None:
    raw = Path(r"C:\Users\v-353\Downloads\AyuGram Desktop\ChatExport_2026-06-07\result.json")
    if not raw.exists():
        pytest.skip("raw result.json sample not available")
    sample = tmp_path / "result.json"
    sample.write_text(raw.read_text(encoding="utf-8")[:250_000], encoding="utf-8")
    text = sample.read_text(encoding="utf-8", errors="ignore")
    if not text.rstrip().endswith("}"):
        shutil.copy(raw, sample)
    ensure_workspace()

    assert run_cli(["tg-import", str(sample), "--profile", "raw_sample"]) == 0

    profile_dir = tw_root / "identity_styles" / "raw_sample"
    assert (profile_dir / "raw" / "result.json").exists()
    assert (profile_dir / "parsed" / "telegram_messages_cleaned.jsonl").exists()
    with connect_db() as conn:
        row = conn.execute("select source_role, text_clean from telegram_messages limit 1").fetchone()
    assert row["source_role"] in {"own_original", "own_forwarded_self", "forwarded_other", "service", "empty_or_media_only"}
    assert isinstance(row["text_clean"], str)


def test_style_build_creates_identity_support_files(tw_root: Path) -> None:
    pack_dir = Path(r"C:\Users\v-353\Downloads\tg_identity_pack")
    if not pack_dir.exists():
        pytest.skip("identity pack folder not available")
    ensure_workspace()
    assert run_cli(["tg-import", str(pack_dir), "--profile", "tg_crypto_clean"]) == 0

    assert run_cli(["style-build", "tg_crypto_clean", "--auto"]) == 0

    profile_dir = tw_root / "identity_styles" / "tg_crypto_clean"
    for name in [
        "identity_style_card.md",
        "phrasebank.md",
        "hooks.md",
        "rhythm.md",
        "anti_patterns.md",
        "adaptation_rules.md",
        "self_writing_cheatsheet.md",
        "auto_selection_report.md",
        "auto_gold_examples.md",
        "auto_rejected_examples.md",
        "style_stats.md",
    ]:
        assert (profile_dir / name).exists()
    with connect_db() as conn:
        profile = conn.execute(
            "select profile_name, status from identity_style_profiles where profile_name = ?",
            ("tg_crypto_clean",),
        ).fetchone()
        auto_forwarded = conn.execute(
            """
            select count(*)
            from identity_style_examples e
            join telegram_messages m
              on m.profile_name = e.profile_name
             and m.telegram_message_id = e.telegram_message_id
            where e.label = 'auto_gold'
              and m.source_role = 'forwarded_other'
            """
        ).fetchone()[0]
    assert profile["status"] == "built"
    assert auto_forwarded == 0


def test_style_stats_and_refresh_commands(tw_root: Path) -> None:
    pack_dir = Path(r"C:\Users\v-353\Downloads\tg_identity_pack")
    if not pack_dir.exists():
        pytest.skip("identity pack folder not available")
    ensure_workspace()
    assert run_cli(["tg-import", str(pack_dir), "--profile", "tg_crypto_clean"]) == 0

    assert run_cli(["style-refresh", "tg_crypto_clean"]) == 0
    assert run_cli(["style-stats", "tg_crypto_clean"]) == 0

    profile_dir = tw_root / "identity_styles" / "tg_crypto_clean"
    assert (profile_dir / "style_stats.md").exists()


def test_style_learn_uses_only_approved_own_texts(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "style-learn-project"
    project.mkdir()
    ensure_workspace()

    ready = create_draft("ready text about validation protocol breaking", "short", project, no_llm=True)
    posted = create_draft("posted text about execution assumptions", "short", project, no_llm=True)
    rejected = create_draft("rejected text about alpha 100x easy money", "short", project, no_llm=True)
    draft_only = create_draft("draft only text that should not be style", "short", project, no_llm=True)

    assert run_cli(["use", ready.id], cwd=project) == 0
    assert run_cli(["ready"], cwd=project) == 0
    assert run_cli(["use", posted.id], cwd=project) == 0
    assert run_cli(["posted", "--url", "https://x.com/example/status/1"], cwd=project) == 0
    assert run_cli(["use", rejected.id], cwd=project) == 0
    assert run_cli(["reject"], cwd=project) == 0
    capsys.readouterr()

    assert run_cli(["style-learn"], cwd=project) == 0
    output = capsys.readouterr().out

    profile_dir = tw_root / "identity_styles" / "tg_crypto_clean"
    assert "processed_posts_report.md" in output
    assert (profile_dir / "processed_posts_report.md").exists()
    assert (profile_dir / "post_gold_examples.md").exists()
    assert (profile_dir / "style_stats.md").exists()

    with connect_db() as conn:
        rows = conn.execute(
            "select source_kind, source_id, text, label from processed_style_examples order by source_kind, source_id"
        ).fetchall()
    learned_text = "\n".join(row["text"] for row in rows)

    assert len(rows) == 2
    assert {row["label"] for row in rows} == {"processed_post_gold"}
    assert "ready text about validation" in learned_text
    assert "posted text about execution" in learned_text
    assert "rejected text" not in learned_text
    assert draft_only.id not in learned_text


def test_identity_style_draft_and_review_create_required_files(
    tw_root: Path, tmp_path: Path
) -> None:
    pack_dir = Path(r"C:\Users\v-353\Downloads\tg_identity_pack")
    if not pack_dir.exists():
        pytest.skip("identity pack folder not available")
    project = tmp_path / "identity-draft"
    project.mkdir()
    ensure_workspace()
    assert run_cli(["tg-import", str(pack_dir), "--profile", "tg_crypto_clean"]) == 0
    assert run_cli(["style-build", "tg_crypto_clean"]) == 0

    assert (
        run_cli(
                [
                    "draft",
                    "--no-llm",
                    "--short",
                    "--algo-aware",
                    "--identity-style",
                "tg_crypto_clean",
                "--identity-strength",
                "0.35",
                "I realized my backtest execution assumptions are fake",
            ],
            cwd=project,
        )
        == 0
    )
    assert run_cli(["style-review", "latest", "--profile", "tg_crypto_clean"], cwd=project) == 0
    draft_id = resolve_draft_id("latest")
    with connect_db() as conn:
        row = conn.execute("select folder_path from drafts where id = ?", (draft_id,)).fetchone()
    folder = Path(row["folder_path"])

    assert (folder / "07_algorithm_review.md").exists()
    assert (folder / "10_identity_style_review.md").exists()
    assert (folder / "11_examples_used.md").exists()
    assert (folder / "12_risk_flags.md").exists()
    examples = (folder / "11_examples_used.md").read_text(encoding="utf-8")
    assert "forwarded_other" not in examples


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
