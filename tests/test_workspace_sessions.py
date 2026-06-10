from __future__ import annotations

from pathlib import Path

from twitter_content_machine.sessions import create_session, find_resumable_session, load_session, save_session


def test_create_session_folder_and_state_json(tw_root: Path) -> None:
    session = create_session()

    assert session.path == tw_root / "sessions" / session.id
    assert (session.path / "SESSION.md").exists()
    assert (session.path / "state.json").exists()
    assert session.status == "active"
    assert session.internal_status == "idle"

    loaded = load_session(session.path)
    assert loaded.id == session.id
    assert loaded.runs == []


def test_find_resumable_session_skips_done_sessions(tw_root: Path) -> None:
    done = create_session()
    done.status = "done"
    done.internal_status = "idle"
    save_session(done)

    active = create_session()
    active.internal_status = "needs_user"
    save_session(active)

    resumed = find_resumable_session()

    assert resumed is not None
    assert resumed.id == active.id


def test_running_session_reopens_as_interrupted(tw_root: Path) -> None:
    session = create_session()
    session.internal_status = "running"
    save_session(session)

    resumed = find_resumable_session()

    assert resumed is not None
    assert resumed.id == session.id
    assert resumed.status == "interrupted"
    assert resumed.internal_status == "needs_user"
