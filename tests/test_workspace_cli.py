from __future__ import annotations

from pathlib import Path

from twitter_content_machine.cli import run_cli


def test_bare_tw_opens_workspace_entrypoint(tw_root: Path, tmp_path: Path, monkeypatch) -> None:
    calls: list[Path | None] = []

    def fake_run_workspace_app(cwd: Path | None = None) -> int:
        calls.append(cwd)
        return 0

    monkeypatch.setattr("twitter_content_machine.workspace_tui.run_workspace_app", fake_run_workspace_app)

    assert run_cli([], cwd=tmp_path) == 0
    assert calls == [tmp_path]


def test_work_command_opens_workspace_entrypoint(tw_root: Path, tmp_path: Path, monkeypatch) -> None:
    calls: list[Path | None] = []

    def fake_run_workspace_app(cwd: Path | None = None) -> int:
        calls.append(cwd)
        return 0

    monkeypatch.setattr("twitter_content_machine.workspace_tui.run_workspace_app", fake_run_workspace_app)

    assert run_cli(["work"], cwd=tmp_path) == 0
    assert calls == [tmp_path]
