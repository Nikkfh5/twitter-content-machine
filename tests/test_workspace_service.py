from __future__ import annotations

from pathlib import Path

from twitter_content_machine.sessions import find_resumable_session, load_session
from twitter_content_machine.workspace_service import ContentWorkspaceService


def test_workspace_draft_creates_session_and_run(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)

    result = service.handle("/draft I found a validation bug")

    assert result.ok is True
    assert result.session is not None
    assert result.run is not None
    assert result.run.input_text == "I found a validation bug"
    assert (result.run.path / "run.json").exists()


def test_continue_advances_local_steps_and_stops_before_codex(
    tw_root: Path, tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict] = []

    def fake_create_draft(**kwargs):
        calls.append(kwargs)
        draft_folder = tw_root / "drafts" / "2026" / "06" / "draft_fake"
        draft_folder.mkdir(parents=True)
        for name in ["FORMAT_DECISION.md", "13_context_bundle.md", "13_context_bundle.json", "14_llm_request.md"]:
            (draft_folder / name).write_text(name, encoding="utf-8")
        (draft_folder / "06_final_candidate.md").write_text("fallback draft", encoding="utf-8")
        return type("Draft", (), {"id": "draft_fake", "folder": draft_folder, "final_text": "fallback draft"})()

    monkeypatch.setattr("twitter_content_machine.workspace_service.create_draft", fake_create_draft)
    service = ContentWorkspaceService(cwd=tmp_path)
    service.handle("/draft raw thought")

    result = service.handle("/continue")

    assert result.ok is True
    assert "Codex" in result.message
    assert calls and calls[0]["no_llm"] is True
    assert result.run is not None
    statuses = {step.id: step.status for step in result.run.steps}
    assert statuses["create_draft"] == "done"
    assert statuses["prepare_codex_contract"] == "done"
    assert statuses["run_codex"] == "pending"


def test_continue_run_executes_codex_and_writes_protocol(
    tw_root: Path, tmp_path: Path, monkeypatch
) -> None:
    def fake_create_draft(**kwargs):
        draft_folder = tw_root / "drafts" / "2026" / "06" / "draft_fake"
        draft_folder.mkdir(parents=True)
        for name in ["FORMAT_DECISION.md", "13_context_bundle.md", "13_context_bundle.json", "14_llm_request.md"]:
            (draft_folder / name).write_text(name, encoding="utf-8")
        (draft_folder / "06_final_candidate.md").write_text("fallback draft", encoding="utf-8")
        return type("Draft", (), {"id": "draft_fake", "folder": draft_folder, "final_text": "fallback draft"})()

    class Parsed:
        ok = True
        error = ""
        data = {
            "variants": [{"id": "A", "name": "direct", "text": "Final draft.", "intent": "dwell", "why_it_might_work": "specific", "risks": []}],
            "critique": {"real_point": "specific", "too_generic": False},
            "selected_variant_id": "A",
            "final_candidate": "Final draft.",
        }

    class Result:
        attempted = True
        ok = True
        raw_output = '{"final_candidate":"Final draft."}'
        parsed = Parsed()
        message = "codex ok"

    monkeypatch.setattr("twitter_content_machine.workspace_service.create_draft", fake_create_draft)
    monkeypatch.setattr("twitter_content_machine.workspace_service.run_llm", lambda *args, **kwargs: Result())

    service = ContentWorkspaceService(cwd=tmp_path)
    service.handle("/draft raw thought")
    service.handle("/continue")
    result = service.handle("/continue --run")

    assert result.ok is True
    assert result.run is not None
    assert (result.run.path / "interface_summary.md").exists()
    assert (result.run.path / "interface_summary.json").exists()
    assert (result.run.path / "artifacts.json").exists()
    assert "Final draft." in (tw_root / "drafts" / "2026" / "06" / "draft_fake" / "06_final_candidate.md").read_text(encoding="utf-8")
    statuses = {step.id: step.status for step in result.run.steps}
    assert statuses["run_codex"] == "done"
    assert statuses["mark_needs_user"] == "done"


def test_restarted_workspace_opens_interrupted_session(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)
    service.handle("/draft raw thought")
    session = find_resumable_session()
    assert session is not None
    session.internal_status = "running"
    from twitter_content_machine.sessions import save_session

    save_session(session)

    reopened = ContentWorkspaceService(cwd=tmp_path)

    assert reopened.session is not None
    assert reopened.session.status == "interrupted"


def test_path_and_runs_commands_show_session_state(tw_root: Path, tmp_path: Path) -> None:
    service = ContentWorkspaceService(cwd=tmp_path)
    service.handle("/draft raw thought")

    path_result = service.handle("/path")
    runs_result = service.handle("/runs")

    assert str(tw_root / "sessions") in path_result.message
    assert "draft_generation" in runs_result.message
