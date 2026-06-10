from __future__ import annotations

from pathlib import Path

from twitter_content_machine.runs import (
    append_event,
    create_run,
    default_draft_steps,
    next_unfinished_step,
    read_events,
    save_run,
)
from twitter_content_machine.sessions import create_session


def test_create_run_folder_and_run_json(tw_root: Path, tmp_path: Path) -> None:
    session = create_session()
    run = create_run(session, "draft_generation", "raw idea", cwd=tmp_path)

    assert run.path == session.path / "runs" / run.id
    assert (run.path / "run.json").exists()
    assert run.type == "draft_generation"
    assert run.input_text == "raw idea"
    assert [step.id for step in run.steps] == [step.id for step in default_draft_steps()]


def test_append_and_read_events_jsonl(tw_root: Path) -> None:
    session = create_session()
    run = create_run(session, "draft_generation", "raw idea")

    append_event(run, "step_started", "Draft step started", step_id="create_draft")
    append_event(run, "step_finished", "Draft step finished", step_id="create_draft")

    events = read_events(run)
    assert [event["type"] for event in events] == ["run_created", "step_started", "step_finished"]
    assert events[1]["step_id"] == "create_draft"


def test_next_unfinished_step_skips_done_and_blocks_codex_without_confirmation(tw_root: Path) -> None:
    session = create_session()
    run = create_run(session, "draft_generation", "raw idea")
    run.steps[0].status = "done"
    run.steps[1].status = "done"
    run.steps[2].status = "done"
    run.steps[3].status = "done"
    save_run(run)

    blocked = next_unfinished_step(run, allow_codex=False)
    allowed = next_unfinished_step(run, allow_codex=True)

    assert blocked is None
    assert allowed is not None
    assert allowed.id == "run_codex"
