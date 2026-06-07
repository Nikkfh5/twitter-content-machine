from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import shutil

import pytest

from twitter_content_machine import mcp_server
from twitter_content_machine.cli import run_cli
from twitter_content_machine.config import load_config
from twitter_content_machine.db import connect_db, resolve_draft_id
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
    assert (tw_root / "identity_styles").exists()
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
    assert {
        "projects",
        "ideas",
        "drafts",
        "posts",
        "sources",
        "telegram_messages",
        "identity_style_profiles",
        "identity_style_examples",
        "drafts_fts",
        "telegram_messages_fts",
    } <= tables


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
    draft = create_draft(text, "short", project)

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
    )

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "financial-advice risk" in review
    assert "crypto-shill risk" in review
    assert "decision: reject" in review


def test_media_plan_rejects_decorative_media(tw_root: Path, tmp_path: Path) -> None:
    project = tmp_path / "media"
    project.mkdir()
    ensure_workspace()
    draft = create_draft(
        "Small note: the useful lesson was that validation leaked through the feature protocol",
        "short",
        project,
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
    draft = create_draft("backtesting assumptions matter", "thread", project)
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

    assert run_cli(["style-build", "tg_crypto_clean"]) == 0

    profile_dir = tw_root / "identity_styles" / "tg_crypto_clean"
    for name in [
        "identity_style_card.md",
        "phrasebank.md",
        "hooks.md",
        "rhythm.md",
        "anti_patterns.md",
        "adaptation_rules.md",
        "self_writing_cheatsheet.md",
    ]:
        assert (profile_dir / name).exists()
    with connect_db() as conn:
        profile = conn.execute(
            "select profile_name, status from identity_style_profiles where profile_name = ?",
            ("tg_crypto_clean",),
        ).fetchone()
    assert profile["status"] == "built"


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
        "tw_style_curate",
    ]:
        assert name in tool_names
    assert all("publish" not in name and "post_to_x" not in name for name in tool_names)
