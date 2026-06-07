from __future__ import annotations

from pathlib import Path

from .db import connect_db, latest_draft_id, resolve_draft_id
from .workspace import ensure_workspace


ACTIVE_ALIASES = {"", ".", "current", "active"}


def current_draft_state_path() -> Path:
    workspace = ensure_workspace()
    return workspace.root / "state" / "current_draft.txt"


def set_current_draft(draft_id: str) -> None:
    path = current_draft_state_path()
    path.write_text(draft_id.strip() + "\n", encoding="utf-8")


def get_current_draft_id() -> str | None:
    path = current_draft_state_path()
    if path.exists():
        draft_id = path.read_text(encoding="utf-8", errors="replace").strip()
        if draft_id and _draft_exists(draft_id):
            return draft_id
    return latest_draft_id()


def resolve_active_draft_id(value: str | None = None) -> str:
    if value is None or value.strip() in ACTIVE_ALIASES:
        draft_id = get_current_draft_id()
        if not draft_id:
            raise ValueError("No active draft. Create one with: tw draft \"text\"")
        return draft_id
    return resolve_draft_id(value)


def draft_id_from_list_number(value: str, rows: list[dict]) -> str | None:
    if not value.isdigit():
        return None
    index = int(value) - 1
    if index < 0 or index >= len(rows):
        raise ValueError(f"Draft number out of range: {value}")
    return str(rows[index]["id"])


def _draft_exists(draft_id: str) -> bool:
    with connect_db() as conn:
        row = conn.execute("select 1 from drafts where id = ?", (draft_id,)).fetchone()
    return row is not None
