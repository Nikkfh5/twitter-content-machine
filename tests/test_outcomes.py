from __future__ import annotations

from pathlib import Path

import pytest

from twitter_content_machine.cli import run_cli
from twitter_content_machine.db import connect_db, resolve_draft_id
from twitter_content_machine.drafting import create_draft
from twitter_content_machine.workspace import ensure_workspace


def test_outcome_command_records_high_value_interaction(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "outcome-project"
    project.mkdir()
    ensure_workspace()
    draft = create_draft("build log about execution checks", "build-log", project, no_llm=True)

    assert (
        run_cli(
            [
                "outcome",
                "latest",
                "--handle",
                "@quantdev",
                "--action",
                "reply",
                "--why",
                "relevant microstructure builder",
                "--cluster",
                "quant",
                "--relationship",
                "builder",
                "--quality-note",
                "asked useful question",
                "--follow-up",
            ],
            cwd=project,
        )
        == 0
    )
    output = capsys.readouterr().out
    artifact = draft.folder / "20_high_value_interactions.md"
    text = artifact.read_text(encoding="utf-8")

    assert "recorded outcome" in output
    assert "@quantdev" in text
    assert "relevant microstructure builder" in text
    assert "follow_up_needed: true" in text
    with connect_db() as conn:
        interaction = conn.execute("select handle, action, audience_cluster from high_value_interactions").fetchone()
        account = conn.execute("select handle, cluster, why_important from accounts").fetchone()
    assert interaction["handle"] == "@quantdev"
    assert interaction["action"] == "reply"
    assert interaction["audience_cluster"] == "quant"
    assert account["handle"] == "@quantdev"
    assert account["cluster"] == "quant"


def test_outcomes_command_lists_current_draft_interactions(
    tw_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "outcomes-list"
    project.mkdir()
    ensure_workspace()
    create_draft("note about validation protocol", "adaptive", project, no_llm=True)

    assert (
        run_cli(
            [
                "outcome",
                "latest",
                "--handle",
                "@mlinfra",
                "--action",
                "repost",
                "--why",
                "ML infra account with relevant audience",
            ],
            cwd=project,
        )
        == 0
    )
    capsys.readouterr()

    assert run_cli(["outcomes"], cwd=project) == 0
    output = capsys.readouterr().out

    assert "@mlinfra" in output
    assert "repost" in output
    assert "ML infra account" in output
    assert resolve_draft_id("latest") in output
