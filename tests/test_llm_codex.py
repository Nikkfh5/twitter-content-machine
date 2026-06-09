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
