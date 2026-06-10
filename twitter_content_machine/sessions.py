from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import get_now, iso_now
from .workspace import ensure_workspace


USER_STATUSES = {"active", "interrupted", "done"}
INTERNAL_STATUSES = {"idle", "running", "needs_user", "failed"}


@dataclass
class ContentSession:
    id: str
    path: Path
    created_at: str
    updated_at: str
    status: str = "active"
    internal_status: str = "idle"
    draft_id: str | None = None
    current_run_id: str | None = None
    runs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": str(self.path),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "internal_status": self.internal_status,
            "draft_id": self.draft_id,
            "current_run_id": self.current_run_id,
            "runs": self.runs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> "ContentSession":
        session_path = path or Path(str(data["path"]))
        status = str(data.get("status", "active"))
        internal_status = str(data.get("internal_status", "idle"))
        if status not in USER_STATUSES:
            status = "active"
        if internal_status not in INTERNAL_STATUSES:
            internal_status = "idle"
        return cls(
            id=str(data["id"]),
            path=session_path,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", data.get("created_at", ""))),
            status=status,
            internal_status=internal_status,
            draft_id=data.get("draft_id"),
            current_run_id=data.get("current_run_id"),
            runs=[str(item) for item in data.get("runs", [])],
        )


def sessions_root(root: Path | None = None) -> Path:
    workspace = ensure_workspace(root)
    path = workspace.root / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_session(root: Path | None = None) -> ContentSession:
    root_path = sessions_root(root)
    session_id = _unique_session_id(root_path)
    session_path = root_path / session_id
    session_path.mkdir(parents=True, exist_ok=False)
    (session_path / "runs").mkdir()
    now = iso_now()
    session = ContentSession(
        id=session_id,
        path=session_path,
        created_at=now,
        updated_at=now,
    )
    (session_path / "SESSION.md").write_text(_session_md(session), encoding="utf-8")
    save_session(session)
    return session


def load_session(path: Path) -> ContentSession:
    state_path = path / "state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    return ContentSession.from_dict(data, path=path)


def save_session(session: ContentSession) -> None:
    session.updated_at = iso_now()
    session.path.mkdir(parents=True, exist_ok=True)
    (session.path / "state.json").write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (session.path / "SESSION.md").write_text(_session_md(session), encoding="utf-8")


def find_resumable_session(root: Path | None = None) -> ContentSession | None:
    candidates: list[ContentSession] = []
    for state_path in sessions_root(root).glob("*/state.json"):
        try:
            session = load_session(state_path.parent)
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        if session.status == "done":
            continue
        if session.internal_status == "running":
            session.status = "interrupted"
            session.internal_status = "needs_user"
            save_session(session)
        if session.status in {"active", "interrupted"}:
            candidates.append(session)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.updated_at, item.id), reverse=True)[0]


def _unique_session_id(root: Path) -> str:
    base = f"{get_now():%Y%m%d-%H%M%S}-workspace"
    candidate = base
    counter = 2
    while (root / candidate).exists():
        candidate = f"{base}-{counter:02d}"
        counter += 1
    return candidate


def _session_md(session: ContentSession) -> str:
    return f"""# Content Workspace Session

- id: {session.id}
- status: {session.status}
- internal_status: {session.internal_status}
- draft_id: {session.draft_id or ""}
- current_run_id: {session.current_run_id or ""}
- created_at: {session.created_at}
- updated_at: {session.updated_at}
"""
