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
