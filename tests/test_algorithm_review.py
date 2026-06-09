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

def test_algo_review_does_not_treat_captured_idea_as_repeated_post(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "repeat-check"
    project.mkdir()
    ensure_workspace()
    text = "Backtesting realism improved only after I stopped trusting fake fills"
    assert run_cli(["idea", text], cwd=project) == 0
    draft = create_draft(text, "adaptive", project, no_llm=True)

    assert run_cli(["algo-review", draft.id], cwd=project) == 0
    review = (draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "repeated idea risk: low" in review
    assert "similar memory exists" not in review

def test_algo_review_does_not_treat_plain_draft_as_repeated_post(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "plain-draft-repeat"
    project.mkdir()
    ensure_workspace()
    text = "Benchmark realism improved only after repeated checks exposed weak baselines"
    create_draft(f"{text} in the first version", "adaptive", project, no_llm=True)
    new_draft = create_draft(text, "adaptive", project, no_llm=True)

    assert run_cli(["algo-review", new_draft.id], cwd=project) == 0
    review = (new_draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "repeated idea risk: low" in review
    assert "plain draft" not in review

def test_algo_review_flags_ready_or_posted_drafts_as_repeated(
    tw_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "ready-repeat"
    project.mkdir()
    ensure_workspace()
    text = "Benchmark realism improved only after repeated checks exposed weak baselines"
    old_draft = create_draft(f"{text} in the first version", "adaptive", project, no_llm=True)
    set_draft_status(old_draft.id, "ready")
    new_draft = create_draft(text, "adaptive", project, no_llm=True)

    assert run_cli(["algo-review", new_draft.id], cwd=project) == 0
    review = (new_draft.folder / "07_algorithm_review.md").read_text(encoding="utf-8").lower()

    assert "repeated idea risk: high" in review
    assert "similar memory exists: ready draft" in review

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
